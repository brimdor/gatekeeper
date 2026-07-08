
import argparse
import subprocess
import sys

def bump_version(current_version, bump_type, pre_release=None):
    # Simple semver parser
    import re
    match = re.match(r"v?(\d+)\.(\d+)\.(\d+)(?:-rc\.(\d+))?", current_version)
    if not match:
        print(f"Error: Could not parse version {current_version}")
        sys.exit(1)
    
    major, minor, patch, rc = match.groups()
    major, minor, patch = int(major), int(minor), int(patch)
    rc = int(rc) if rc else 0
    
    if bump_type == "major":
        major += 1; minor = 0; patch = 0; rc = 0
    elif bump_type == "minor":
        minor += 1; patch = 0; rc = 0
    elif bump_type == "patch":
        patch += 1; rc = 0
    
    new_version = f"v{major}.{minor}.{patch}"
    if pre_release:
        # If it's an RC, it's usually rc.1 for a new bump, or rc.N+1 if already an rc
        # For simplicity, we'll assume rc.1 if not specified or just increment if target is rc
        new_version += f"-rc.{pre_release}"
        
    return new_version

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--current", required=True)
    parser.add_argument("--bump", choices=["major", "minor", "patch"], required=True)
    parser.add_argument("--pre-release", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    
    new_ver = bump_version(args.current, args.bump, args.pre_release)
    print(f"Bumping {args.current} -> {new_ver}")
    
    if not args.dry_run:
        subprocess.run(["git", "tag", new_ver], check=True)
        subprocess.run(["git", "push", "origin", new_ver], check=True)

if __name__ == "__main__":
    main()
