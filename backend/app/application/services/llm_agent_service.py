import json
import logging
import re
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services.sfdx_mcp_service import SFDXMCPService
from app.core.config import get_settings

logger = logging.getLogger("cloudbridge.llm_agent")

class LLMAgentService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()

    async def _call_llm(self, prompt: str) -> str:
        """Call the Custom LLM API matching the user's specific JSON configuration."""
        if not self.settings.llm_endpoint_url or not self.settings.llm_api_key:
            raise ValueError("LLM_ENDPOINT_URL or LLM_API_KEY environment variable is missing.")

        payload = {
            "model_id": self.settings.llm_model or "389",
            "prompt": prompt
        }
        
        headers = {
            "Authorization": f"Bearer {self.settings.llm_api_key}",
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient(timeout=180.0) as client:
            resp = await client.post(self.settings.llm_endpoint_url, json=payload, headers=headers)
            if resp.status_code != 200:
                logger.error(f"LLM API Error {resp.status_code}: {resp.text}")
                resp.raise_for_status()
                
            data = resp.json()
            # Try to adapt to standard open-world schemas, usually completion text is under 'text' or 'choices'
            if "completion" in data:
                return data["completion"]
            if "text" in data:
                return data["text"]
            if "choices" in data and isinstance(data["choices"], list):
                choice = data["choices"][0]
                return choice.get("text", choice.get("message", {}).get("content", ""))
            
            # fallback to dumping the whole json and letting the string parser figure it out later
            return json.dumps(data)

    async def run_chat_loop(self, org_id: uuid.UUID, user_prompt: str) -> AsyncGenerator[dict[str, Any], None]:
        mcp_service = SFDXMCPService(self.db)
        yield {"phase": "init", "msg": "Fetching available tools for org..."}
        
        tools_resp = await mcp_service.list_tools_for_org(org_id)
        if tools_resp.get("status") != "success":
            yield {"phase": "error", "msg": f"Failed to list tools: {tools_resp.get('error')}"}
            return
            
        tools = tools_resp.get("tools", [])
        tool_descriptions = "\n".join([f"- {t['name']}: {t.get('description', '')}. Schema: {json.dumps(t.get('inputSchema', {}))}" for t in tools])
        tool_names = ", ".join([f"'{t['name']}'" for t in tools])

        system_prompt = f"""You are an expert Salesforce system administrator and developer AI.
You have access to the following tools:
{tool_descriptions}

Use the following format to solve the user's request:
Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action in valid JSON format
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final message back to the user

Begin!

Question: {user_prompt}
"""
        
        current_prompt = system_prompt
        max_iterations = 10
        
        for iteration in range(max_iterations):
            yield {"phase": "llm_call", "msg": f"Thinking (step {iteration + 1})..."}
            
            try:
                llm_response = await self._call_llm(current_prompt)
            except Exception as e:
                yield {"phase": "error", "msg": f"LLM error: {str(e)}"}
                return
                
            current_prompt += f"\n{llm_response}\n"
            
            if "Final Answer:" in llm_response:
                final_answer = llm_response.split("Final Answer:")[-1].strip()
                yield {"phase": "done", "msg": "Completed task.", "result": final_answer}
                return

            if "Action:" in llm_response and "Action Input:" in llm_response:
                # Parse action & input
                try:
                    action_part = llm_response.split("Action:")[1].split("\n")[0].strip()
                    action_input_part = llm_response.split("Action Input:")[1].split("Observation:")[0].split("\nThought:")[0].strip()
                    
                    # Sometimes LLM wraps JSON in markdown blocks
                    if action_input_part.startswith("```json"):
                        action_input_part = action_input_part[7:]
                    if action_input_part.startswith("```"):
                        action_input_part = action_input_part[3:]
                    if action_input_part.endswith("```"):
                        action_input_part = action_input_part[:-3]
                        
                    try:
                        # Try to extract just the json part using regex
                        match = re.search(r'\{.*\}', action_input_part, re.DOTALL)
                        if match:
                            action_input_part = match.group(0)
                        action_args = json.loads(action_input_part)
                    except json.JSONDecodeError as exc:
                        raise ValueError(f'Invalid JSON: {action_input_part}') from exc
                except Exception as e:
                    current_prompt += f"Observation: ERROR parsing Action or Action Input JSON string: {e}. Make sure to only respond with valid JSON after Action Input:\nThought:"
                    continue
                    
                yield {"phase": "tool_call", "msg": f"Running tool: {action_part}"}
                
                # Execute tool via SFDXMCPService
                tool_result = await mcp_service.run_tool(org_id, action_part, action_args)
                
                # Convert the tool execution report into text
                if tool_result.get("status") == "success":
                    obs = json.dumps(tool_result.get("result", {}))
                else:
                    obs = f"ERROR: {tool_result.get('error', 'unknown error')}"
                
                # Truncate if crazy long
                if len(obs) > 5000:
                    obs = obs[:5000] + "...(truncated)"
                    
                current_prompt += f"Observation: {obs}\nThought:"
            else:
                # Missing action, but no final answer
                current_prompt += "Observation: You did not provide an Action nor a Final Answer. Please follow the format strictly.\nThought:"
                
        yield {"phase": "error", "msg": "Max iterations reached without a Final Answer."}
