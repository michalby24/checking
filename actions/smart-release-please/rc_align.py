import os
import re
import subprocess
import sys
import json

# Configuration
BOT_COMMIT_MSG = "chore: enforce correct rc version"
BOT_FOOTER_TAG = "Release-As:"
MANIFEST_FILE = ".release-please-manifest.json"

def run_git_command(args, fail_on_error=True):
    try:
        result = subprocess.run(["git"] + args, stdout=subprocess.PIPE, text=True, check=fail_on_error)
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None

def get_current_branch():
    # Use GITHUB_REF_NAME if available, else git rev-parse
    return os.environ.get("GITHUB_REF_NAME", run_git_command(["rev-parse", "--abbrev-ref", "HEAD"]))

# ------------------------------------------------------------------
# LOGIC FOR MAIN BRANCH (Promote RC -> Stable)
# ------------------------------------------------------------------
def handle_main_branch():
    print("INFO: Detected 'main' branch. Checking manifest for RC cleanup...")
    
    if not os.path.exists(MANIFEST_FILE):
        print("INFO: No manifest file found. Nothing to do.")
        return None

    try:
        with open(MANIFEST_FILE, 'r') as f:
            data = json.load(f)
        
        # Assume package is "." - adjust if you use named packages
        current_ver = data.get(".", "")
        
        if "-" in current_ver:
            # Strip everything after the first hyphen (0.0.1-rc.3 -> 0.0.1)
            stable_ver = current_ver.split("-")[0]
            print(f"NOTICE: Found Pre-release '{current_ver}'. promoting to '{stable_ver}'")
            return stable_ver
        else:
            print(f"INFO: Version '{current_ver}' is already stable.")
            return None

    except Exception as e:
        print(f"ERROR: Failed to read manifest: {e}")
        return None

# ------------------------------------------------------------------
# LOGIC FOR NEXT BRANCH (Calculate Next RC)
# ------------------------------------------------------------------
def handle_next_branch():
    # ... (Your existing calculation logic) ...
    # I will condense your previous logic here for brevity, 
    # but strictly reusing your 'find_baseline_tag', 'get_commit_depth', etc.
    
    # 1. Find Baseline
    rc_tag = run_git_command(["describe", "--tags", "--match", "v*-rc*", "--abbrev=0"], fail_on_error=False)
    stable_tag = run_git_command(["describe", "--tags", "--match", "v*", "--exclude", "*-rc*", "--abbrev=0"], fail_on_error=False)
    
    tag = rc_tag if rc_tag else stable_tag
    from_stable = bool(stable_tag and not rc_tag)

    if not tag and not stable_tag:
         # Fallback for empty repo
         tag = None
         from_stable = True

    # 2. Get Depth
    rev_range = f"{tag}..HEAD" if tag else "HEAD"
    raw_subjects = run_git_command(["log", rev_range, "--first-parent", "--pretty=format:%s"], fail_on_error=False)
    
    if not raw_subjects:
        print("INFO: No commits found since baseline.")
        return None

    # Filter commits (Loop Protection & Bot Filter)
    depth = 0
    for s in raw_subjects.split('\n'):
        if BOT_FOOTER_TAG in s or BOT_COMMIT_MSG in s: continue
        if re.match(r"^chore(\(.*\))?: release", s): continue
        depth += 1

    if depth == 0:
        return None

    # 3. Parse Semver
    major, minor, patch, rc = 0, 0, 0, 0
    if tag:
        # (Reuse your regex parsing logic here)
        m_rc = re.match(r"^v(\d+)\.(\d+)\.(\d+)-rc\.(\d+)$", tag)
        m_stable = re.match(r"^v(\d+)\.(\d+)\.(\d+)$", tag)
        if m_rc:
            major, minor, patch, rc = map(int, m_rc.groups())
        elif m_stable:
            major, minor, patch = map(int, m_stable.groups())

    # 4. Analyze Impact
    logs = run_git_command(["log", rev_range, "--pretty=format:%B"], fail_on_error=False) or ""
    breaking_regex = r"^(feat|fix|refactor)(\(.*\))?!:"
    is_breaking = re.search(breaking_regex, logs, re.MULTILINE) or "BREAKING CHANGE" in logs
    is_feat = re.search(r"^feat(\(.*\))?:", logs, re.MULTILINE)

    # 5. Calculate
    if is_breaking:
        return f"{major + 1}.0.0-rc.{depth}"
    
    if is_feat:
        if from_stable or patch > 0:
            return f"{major}.{minor + 1}.0-rc.{depth}"
        else:
            return f"{major}.{minor}.{patch}-rc.{rc + depth}"

    if from_stable:
        return f"{major}.{minor}.{patch + 1}-rc.{depth}"
    else:
        return f"{major}.{minor}.{patch}-rc.{rc + depth}"

# ------------------------------------------------------------------
# MAIN ENTRYPOINT
# ------------------------------------------------------------------
def main():
    branch = get_current_branch()
    next_ver = None

    if branch == "main":
        next_ver = handle_main_branch()
    elif branch == "next":
        next_ver = handle_next_branch()
    else:
        print(f"INFO: Branch '{branch}' is not managed (only main/next).")

    if next_ver:
        print(f"RESULT: Calculated target version: {next_ver}")
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"next_version={next_ver}\n")
    else:
        print("RESULT: No version update required.")

if __name__ == "__main__":
    main()
