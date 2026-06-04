# AI Dependency Graph + Auto Package Builder

## Overview

The **AI Dependency Graph + Auto Package Builder** is a Salesforce-native feature that automatically discovers metadata dependencies, detects missing components, and generates deployment packages with proper ordering.

## Why This Feature?

Salesforce deployments fail because dependencies are hard to track manually. This feature solves that by:

1. **Automatic Discovery**: AI analyzes your metadata and discovers all dependencies
2. **Missing Detection**: Identifies components you forgot to include
3. **Smart Ordering**: Generates topologically-sorted deployment order
4. **One-Click Fix**: Auto-adds missing dependencies with a single click

## Key Features

### 1. AI-Powered Dependency Discovery

The system automatically discovers:

```
Flow
  ↓
Apex Class
  ↓
Custom Metadata
  ↓
Permission Set
  ↓
Integration
  ↓
Profiles
```

**Example Output:**
```
Missing:
- Permission Set: Opportunity_Approver
- Custom Metadata: Integration_Settings

Add automatically? [Y]
```

### 2. Automatic Package Generation

- **Deployment Order**: Components sorted by dependency (Custom Objects → Apex → Flows)
- **Validation Order**: Reverse order for safety checks
- **Package.xml**: Auto-generated with all dependencies included

### 3. Interactive UI

- Visual dependency graph
- Missing dependencies highlighted by severity
- One-click auto-add for missing components
- Download generated package.xml

## API Endpoints

### Build Dependency Graph

```http
POST /api/v1/dependency-graph/build
Content-Type: application/json

{
  "org_id": "uuid",
  "components": {
    "Flow": ["Opportunity_Approval_Flow"],
    "ApexClass": ["OpportunityTriggerHandler"]
  },
  "include_missing": true,
  "generate_package": true
}
```

**Response:**
```json
{
  "analysis_id": "uuid",
  "graph": {
    "nodes": [...],
    "edges": [...],
    "stats": {
      "total_nodes": 15,
      "total_edges": 23,
      "changed_components": 2,
      "impacted_components": 13,
      "missing_dependencies": 3
    }
  },
  "missing_dependencies": [
    {
      "type": "PermissionSet",
      "name": "Opportunity_Approver",
      "required_by": ["Flow:Opportunity_Approval_Flow"],
      "severity": "high",
      "auto_addable": true,
      "reason": "Flow requires this permission set for user access"
    }
  ],
  "deployment_order": [
    "CustomMetadata:Integration_Settings",
    "ApexClass:OpportunityTriggerHandler",
    "Flow:Opportunity_Approval_Flow",
    "PermissionSet:Opportunity_Approver"
  ],
  "validation_order": [...],
  "package_xml": "<?xml version=\"1.0\"?>..."
}
```

### Get Existing Graph

```http
GET /api/v1/dependency-graph/{analysis_id}
```

### Auto-Add Missing Dependencies

```http
POST /api/v1/dependency-graph/{analysis_id}/missing-dependencies/add
Content-Type: application/json

["PermissionSet", "CustomMetadata"]
```

### Build Auto Package

```http
POST /api/v1/dependency-graph/auto-package
Content-Type: application/json

{
  "analysis_id": "uuid",
  "auto_add_missing": true,
  "include_profiles": true,
  "include_permission_sets": true
}
```

## Usage Examples

### Example 1: Basic Dependency Analysis

```python
# Create impact analysis
analysis = await impact_service.create_analysis({
    "org_id": org_id,
    "changed_items": {
        "Flow": ["Opportunity_Approval_Flow"],
        "ApexClass": ["OpportunityService"]
    },
    "build_dependency_graph": True
})

# Run analysis (includes dependency graph building)
result = await impact_service.run_analysis(
    analysis.id,
    build_dependency_graph=True
)

# Access results
print(f"Missing: {len(result.missing_dependencies)} components")
print(f"Deployment order: {result.deployment_order}")
```

### Example 2: Auto-Add Missing Dependencies

```typescript
// Frontend: Build graph and auto-add missing
const response = await fetch('/api/v1/dependency-graph/build', {
  method: 'POST',
  body: JSON.stringify({
    org_id: orgId,
    components: {
      Flow: ['Opportunity_Approval_Flow'],
      ApexClass: ['OpportunityTriggerHandler']
    },
    include_missing: true,
    generate_package: true
  })
});

const graph = await response.json();

// Auto-add critical missing dependencies
if (graph.missing_dependencies.length > 0) {
  await fetch(`/api/v1/dependency-graph/${graph.analysis_id}/missing-dependencies/add`, {
    method: 'POST',
    body: JSON.stringify(['PermissionSet', 'CustomMetadata'])
  });
}
```

### Example 3: Deploy with Auto-Generated Package

```python
# Build dependency graph
graph_result = await graph_service.build_dependency_graph(
    analysis_id=analysis.id,
    components=changed_items,
    include_missing=True,
    use_ai=True
)

# Create deployment with auto-generated package
deployment = await deployment_service.create_deployment({
    "org_id": org_id,
    "artifact_key": graph_result["package_xml"],
    "deployment_type": "validate_only",
    "intelligence_analysis_id": analysis.id
})

# Run deployment
await deployment_service.start_deployment(deployment)
```

## AI-Enhanced Dependency Rules

The system uses AI to enhance basic dependency rules:

### Basic Rules (Rule-Based)
```python
DEPENDENCY_RULES = {
    "Flow": ["ApexClass", "CustomObject", "PermissionSet"],
    "ApexClass": ["CustomObject", "CustomMetadata"],
    "CustomObject": ["CustomField", "RecordType", "PermissionSet"]
}
```

### AI Enhancement
The LLM analyzes actual metadata content to discover:
- Dynamic Apex references
- Flow action calls
- Custom metadata relationships
- Permission dependencies
- Profile requirements

## Deployment Order Priority

Components are deployed in this order (lower = first):

1. **CustomMetadata** (1) - Configuration first
2. **CustomObject** (2) - Data model
3. **CustomField** (3) - Object extensions
4. **RecordType** (4) - Record types
5. **ValidationRule** (6) - Validation logic
6. **ApexClass** (7) - Business logic
7. **ApexTrigger** (8) - Triggers
8. **Flow** (9) - Automation
9. **PermissionSet** (12) - Security
10. **Profile** (13) - User access
11. **Layout** (14) - UI

## Frontend Integration

The feature includes a complete React UI at `/dependency-graph`:

### Features:
- ✅ Visual dependency graph with nodes and edges
- ✅ Missing dependencies panel with severity indicators
- ✅ One-click auto-add for missing components
- ✅ Deployment order visualization
- ✅ Package.xml preview and download
- ✅ Direct integration with deployment workflow

### Navigation:
```
Impact Analysis → Dependency Graph → Deploy
```

## Database Schema

### New Fields in `impact_analyses` Table:

```sql
dependency_graph JSON          -- Full graph structure
missing_dependencies JSON      -- Missing components list
deployment_order JSON          -- Ordered deployment sequence
validation_order JSON          -- Ordered validation sequence
auto_package_generated BOOLEAN -- Package auto-generated flag
package_metadata JSON          -- Package generation metadata
```

### Indexes:
```sql
CREATE INDEX ix_metadata_dependencies_source 
  ON metadata_dependencies(source_type, source_name);
  
CREATE INDEX ix_metadata_dependencies_target 
  ON metadata_dependencies(target_type, target_name);
```

## Configuration

### Environment Variables:

```bash
# Enable AI-powered dependency discovery
LLM_ENDPOINT_URL=https://api.your-llm.com/v1/completions
LLM_API_KEY=your-api-key
LLM_MODEL=389  # Your model ID
```

### Feature Flags:

```python
# In impact analysis creation
{
  "build_dependency_graph": True,  # Enable graph building
  "auto_add_missing": False,       # Auto-add missing deps
}
```

## Best Practices

### 1. Always Build Dependency Graph Before Deployment
```python
# ✅ Good
analysis = await create_analysis(changed_items, build_dependency_graph=True)
await run_analysis(analysis.id)
deployment = await create_deployment_from_analysis(analysis.id)

# ❌ Bad
deployment = await create_deployment(changed_items)  # Missing deps!
```

### 2. Review Missing Dependencies
```python
if analysis.missing_dependencies:
    for dep in analysis.missing_dependencies:
        if dep["severity"] in ["critical", "high"]:
            print(f"⚠️  Missing: {dep['type']}:{dep['name']}")
```

### 3. Use Deployment Order
```python
# Deploy in the order provided by the graph
for component in analysis.deployment_order:
    await deploy_component(component)
```

## Troubleshooting

### Issue: AI Discovery Not Working

**Solution:**
1. Check LLM_ENDPOINT_URL and LLM_API_KEY are set
2. Verify LLM service is accessible
3. Check logs for LLM errors
4. System falls back to rule-based discovery automatically

### Issue: Missing Dependencies Not Detected

**Solution:**
1. Ensure `include_missing=True` in request
2. Check if components are in DEPENDENCY_RULES
3. Review AI prompt for your metadata types
4. Add custom rules to DEPENDENCY_RULES dict

### Issue: Deployment Order Incorrect

**Solution:**
1. Check for circular dependencies in graph
2. Verify DEPLOYMENT_PRIORITY values
3. Review topological sort algorithm
4. Check edge directions in dependency graph

## Performance

- **Graph Building**: ~2-5 seconds for 50 components
- **AI Discovery**: +3-10 seconds (with LLM)
- **Package Generation**: <1 second
- **Memory**: ~10MB per analysis

## Future Enhancements

- [ ] Visual graph editor for manual adjustments
- [ ] Dependency caching for faster rebuilds
- [ ] Multi-org dependency analysis
- [ ] Dependency impact scoring
- [ ] Historical dependency tracking
- [ ] Automated dependency testing

## Related Features

- **Impact Analysis**: Uses dependency graph for impact calculation
- **Deployment Engine**: Uses deployment order for safe deployments
- **AI Release Intelligence**: Incorporates dependency risks in scoring

## Support

For issues or questions:
- Check logs: `backend/uvicorn.log`
- Review API docs: `/api/v1/docs`
- See examples: `docs/features/examples/`

---

**Made with ❤️ by Bob - Your AI Salesforce DevOps Assistant**