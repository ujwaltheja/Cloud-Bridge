#!/usr/bin/env python3
"""
Generate security secrets for Cloud Bridge.

This script generates SECRET_KEY and FERNET_KEY and updates the .env file.
"""
import secrets
import sys
from pathlib import Path
from cryptography.fernet import Fernet


def generate_secret_key() -> str:
    """Generate a secure SECRET_KEY for JWT."""
    return secrets.token_urlsafe(32)


def generate_fernet_key() -> str:
    """Generate a FERNET_KEY for encryption."""
    return Fernet.generate_key().decode()


def update_env_file(secret_key: str, fernet_key: str):
    """Update .env file with generated keys."""
    # Find .env file (should be in project root)
    env_file = Path(__file__).parent.parent / ".env"
    
    if not env_file.exists():
        print(f"Error: .env file not found at {env_file}")
        print("Please create .env file from .env.example first")
        sys.exit(1)
    
    # Read current content
    content = env_file.read_text()
    
    # Replace SECRET_KEY
    if "SECRET_KEY=your-secret-key-here-change-this-in-production" in content:
        content = content.replace(
            "SECRET_KEY=your-secret-key-here-change-this-in-production",
            f"SECRET_KEY={secret_key}"
        )
        print(f"✓ Updated SECRET_KEY in .env")
    elif "SECRET_KEY=" in content:
        print("⚠ SECRET_KEY already set in .env (not overwriting)")
    else:
        print("⚠ SECRET_KEY not found in .env")
    
    # Update FERNET_KEY if it's the default
    if "FERNET_KEY=wQh5kCBOwZuzT-iQ8iAXlberCThZ6XeBO55Qi2irNnc=" in content:
        content = content.replace(
            "FERNET_KEY=wQh5kCBOwZuzT-iQ8iAXlberCThZ6XeBO55Qi2irNnc=",
            f"FERNET_KEY={fernet_key}"
        )
        print(f"✓ Updated FERNET_KEY in .env")
    else:
        print("⚠ FERNET_KEY already customized (not overwriting)")
    
    # Write back
    env_file.write_text(content)
    print(f"\n✓ .env file updated successfully!")


def main():
    """Main function."""
    print("Generating security secrets for Cloud Bridge...\n")
    
    # Generate keys
    secret_key = generate_secret_key()
    fernet_key = generate_fernet_key()
    
    print("Generated keys:")
    print(f"SECRET_KEY={secret_key}")
    print(f"FERNET_KEY={fernet_key}")
    print()
    
    # Ask user if they want to update .env
    response = input("Update .env file with these keys? (y/n): ").strip().lower()
    
    if response == 'y':
        update_env_file(secret_key, fernet_key)
    else:
        print("\nKeys not saved. You can manually add them to .env:")
        print(f"SECRET_KEY={secret_key}")
        print(f"FERNET_KEY={fernet_key}")


if __name__ == "__main__":
    main()

# Made with Bob
