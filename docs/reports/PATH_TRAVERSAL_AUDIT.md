# Path Traversal Vulnerability Audit - Issue #129

**Date**: 2026-03-09
**Severity**: CRITICAL (8/10)
**CVE Reference**: CVE-2026-26329

## Executive Summary

This audit identifies all file operations in the OpenClaw backend and assesses path traversal vulnerability risks. Path traversal vulnerabilities could allow attackers to read or write arbitrary files on the server, leading to:
- Reading sensitive files (/etc/passwd, .env files, source code)
- Writing malicious files (web shells, backdoors)
- Deleting critical system files
- Bypassing access controls

## Files Analyzed

### 1. HIGH RISK: `backend/services/skill_installation_service.py`
**Lines**: 253-263, 276-277
**Operations**:
- `open(skill_md_path, 'r')` (line 276)
- Uses `os.path.join()` with user-controlled `neuro_package` variable
- Constructs paths from NPM package names

**Vulnerability Details**:
```python
# Line 252-263: VULNERABLE PATH CONSTRUCTION
npm_global_prefix = os.path.expanduser("~/.npm-global")
if not os.path.exists(npm_global_prefix):
    npm_global_prefix = "/opt/homebrew/lib"

skill_md_path = os.path.join(
    npm_global_prefix,
    "node_modules",
    neuro_package,  # ← USER CONTROLLED
    "SKILL.md"
)

# Line 276: VULNERABLE FILE READ
with open(skill_md_path, 'r') as f:
    skill_md_content = f.read()
```

**Attack Vector**:
```python
# Attacker provides malicious package name:
neuro_package = "../../../etc/passwd%00SKILL.md"
# Results in path: ~/.npm-global/node_modules/../../../etc/passwd
# Reads /etc/passwd
```

**Risk Level**: HIGH
- User can control `neuro_package` via API endpoint
- Direct file read without validation
- No path sanitization
- Could read any file accessible to the process

---

### 2. HIGH RISK: `backend/services/openclaw_plugin_service.py`
**Lines**: 134, 163-167
**Operations**:
- `open(self.config_file, "r")` (line 134)
- `open(temp_file, "w")` (line 163)
- `temp_file.rename(self.config_file)` (line 167)

**Vulnerability Details**:
```python
# Line 85-100: config_dir can be user-controlled in __init__
def __init__(self, config_dir: Optional[Path] = None, openclaw_bin: str = "openclaw"):
    if config_dir:
        self.config_dir = config_dir  # ← USER CONTROLLED
    else:
        self.config_dir = Path.home() / ".openclaw"

    self.config_file = self.config_dir / "openclaw.json"

# Line 134: VULNERABLE FILE READ
with open(self.config_file, "r") as f:
    config = json.load(f)

# Line 163-167: VULNERABLE FILE WRITE
temp_file = self.config_file.with_suffix(".json.tmp")
with open(temp_file, "w") as f:
    json.dump(config, f, indent=2)
temp_file.rename(self.config_file)
```

**Attack Vector**:
```python
# If config_dir is passed from user input:
service = OpenClawPluginService(config_dir="/etc")
# Results in: config_file = /etc/openclaw.json
# Can overwrite /etc/openclaw.json
```

**Risk Level**: MEDIUM-HIGH
- config_dir parameter can be controlled if exposed via API
- Could write to arbitrary locations
- Currently not directly exposed via API (uses singleton)

---

### 3. HIGH RISK: `backend/services/openclaw_gateway_proxy_service.py`
**Lines**: 182-184, 208-209, 226-232
**Operations**:
- `open(self.config_file, "r")` (line 182)
- `open(self.config_file, "w")` (line 208)
- `open(temp_file, "w")` (line 228)

**Vulnerability Details**:
```python
# Similar pattern to openclaw_plugin_service.py
def __init__(self, gateway_url: Optional[str] = None, config_dir: Optional[Path] = None):
    if config_dir:
        self.config_dir = config_dir  # ← USER CONTROLLED
    else:
        self.config_dir = Path.home() / ".openclaw"

    self.config_file = self.config_dir / "openclaw.json"
```

**Risk Level**: MEDIUM-HIGH
- Same vulnerability pattern as plugin service
- config_dir parameter controllable if exposed

---

### 4. HIGH RISK: `backend/services/dagger_builder_service.py`
**Lines**: 344-345, 348-349, 574-587, 979-980
**Operations**:
- `dockerfile_path.write_text(context.dockerfile_content)` (line 345)
- `os.path.exists(context.source_path)` (line 348)
- `await self._copy_source_files(context.source_path, build_workspace)` (line 349)
- `os.listdir(source_path)` (line 579)
- `os.path.join(source_path, item)` (line 580)
- `shutil.copytree(s, d, dirs_exist_ok=True)` (line 583)
- `shutil.copy2(s, d)` (line 585)
- `tarfile.open(archive_path, "w:gz")` (line 979)
- `tar.add(artifact_dir, arcname=os.path.basename(artifact_dir))` (line 980)

**Vulnerability Details**:
```python
# Line 336-349: VULNERABLE - User controls source_path
async def build_image(self, context: DaggerBuildContext) -> DaggerBuildResult:
    # ...
    # Copy source files if they exist
    if os.path.exists(context.source_path):  # ← USER CONTROLLED
        await self._copy_source_files(context.source_path, build_workspace)

# Line 574-587: VULNERABLE FILE COPY
async def _copy_source_files(self, source_path: str, dest_path: Path):
    if os.path.isdir(source_path):
        for item in os.listdir(source_path):  # ← Reads from user path
            s = os.path.join(source_path, item)
            d = os.path.join(dest_path, item)
            if os.path.isdir(s):
                shutil.copytree(s, d, dirs_exist_ok=True)  # ← Copies arbitrary dirs
            else:
                shutil.copy2(s, d)  # ← Copies arbitrary files
    else:
        shutil.copy2(source_path, dest_path)
```

**Attack Vector**:
```python
# Attacker creates build context with malicious path:
context = DaggerBuildContext(
    id="malicious",
    name="exploit",
    source_path="/etc",  # ← Copies entire /etc directory
    dockerfile_content="...",
    build_args={},
    environment_vars={},
    secrets={}
)
# Results in: copying /etc/* to build workspace (information disclosure)
```

**Risk Level**: CRITICAL
- Allows reading arbitrary directories
- Can copy sensitive system files to workspace
- workspace_dir could also be controllable
- Could write to arbitrary locations via archive_artifacts

---

### 5. HIGH RISK: `backend/services/wireguard_config_manager.py`
**Lines**: 90, 116, 133-137
**Operations**:
- `Path(config_path)` (line 97 - user controlled in __init__)
- `self.config_path.read_text()` (line 116)
- `tempfile.mkstemp(dir=self.config_path.parent, ...)` (line 133-136)
- `os.fdopen(temp_fd, 'w')` (line 141)
- `shutil.move(temp_path, self.config_path)` (line 148)

**Vulnerability Details**:
```python
# Line 90: VULNERABLE - config_path from env var or user param
def __init__(self, config_path: str = os.getenv("WIREGUARD_CONFIG_PATH",
                                                 os.path.expanduser("~/.wireguard/wg0.conf"))):
    self.config_path = Path(config_path)  # ← USER CONTROLLED

# Line 133-148: Writes to config_path
def _write_config(self, content: str) -> None:
    temp_fd, temp_path = tempfile.mkstemp(
        dir=self.config_path.parent,  # ← Based on user path
        prefix=".wg_",
        suffix=".conf.tmp"
    )
    # Writes to temp file then moves to config_path
    shutil.move(temp_path, self.config_path)
```

**Attack Vector**:
```python
# Via environment variable:
export WIREGUARD_CONFIG_PATH="/etc/passwd"
# Results in overwriting /etc/passwd
```

**Risk Level**: HIGH
- Environment variable controllable in some deployment scenarios
- Could overwrite critical system files
- Requires file system permissions but dangerous if running as root

---

### 6. MEDIUM RISK: `backend/networking/wireguard_keys.py`
**Lines**: 136-150, 189-190
**Operations**:
- `path.parent.mkdir(parents=True, exist_ok=True)` (line 136)
- `os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)` (line 140-144)
- `os.write(fd, private_key.encode('utf-8'))` (line 148)
- `open(path, 'r', encoding='utf-8')` (line 189)

**Vulnerability Details**:
```python
# Line 113-163: store_private_key accepts arbitrary file_path
def store_private_key(private_key: str, file_path: str) -> None:
    # ← file_path is USER CONTROLLED
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)  # ← Creates dirs

    fd = os.open(
        str(path),
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
        0o600
    )
    os.write(fd, private_key.encode('utf-8'))
```

**Attack Vector**:
```python
# If exposed via API:
store_private_key("malicious_content", "/etc/cron.d/backdoor")
# Writes cron job to execute attacker's code
```

**Risk Level**: MEDIUM
- Function takes arbitrary file_path
- Creates parent directories
- Not directly exposed via API (internal use)
- Risk depends on how it's called

---

### 7. LOW RISK: `backend/api/v1/endpoints/skill_installation.py`
**Lines**: 250-256, 268-271
**Operations**:
- `shutil.which(binary_name)` (line 255)
- `os.path.join(gopath, "bin", binary_name)` (line 269)
- `os.path.exists(gobin)` (line 270)
- `os.access(gobin, os.X_OK)` (line 270)

**Vulnerability Details**:
```python
# Line 254-271: Uses skill_data["binary"] for path construction
binary_name = skill_data.get("binary", skill_name)
binary_path = shutil.which(binary_name)  # Searches PATH

if not binary_path and skill_data["method"] == "npm":
    result = subprocess.run(["go", "env", "GOPATH"], ...)
    gopath = result.stdout.strip()
    gobin = os.path.join(gopath, "bin", binary_name)  # ← Potential issue
    if os.path.exists(gobin) and os.access(gobin, os.X_OK):
        binary_path = gobin
```

**Risk Level**: LOW
- binary_name comes from hardcoded INSTALLABLE_SKILLS dict
- Not directly user-controllable
- Read-only operations (checking existence)

---

## Vulnerability Summary

### Critical Risks (3)
1. **dagger_builder_service.py** - Arbitrary file read/copy via source_path
2. **skill_installation_service.py** - Arbitrary file read via package name
3. **wireguard_config_manager.py** - Arbitrary file write via config_path

### High Risks (2)
4. **openclaw_plugin_service.py** - Arbitrary file write if config_dir exposed
5. **openclaw_gateway_proxy_service.py** - Arbitrary file write if config_dir exposed

### Medium Risks (1)
6. **wireguard_keys.py** - Arbitrary file write but internal function

### Low Risks (1)
7. **skill_installation.py** - Read-only, hardcoded paths

## Required Fixes

### 1. Create Secure File Utility Module
Create `backend/utils/file_security.py` with:
- `sanitize_filename()` - Remove path separators, null bytes, leading dots
- `validate_file_path()` - Ensure resolved path stays within base directory
- `safe_read_file()` - Validate path before reading
- `safe_write_file()` - Validate path before writing, atomic writes

### 2. Fix Each Vulnerable File
- **skill_installation_service.py**: Validate NPM package names against whitelist pattern
- **dagger_builder_service.py**: Whitelist allowed source paths, validate against workspace
- **wireguard_config_manager.py**: Validate config_path stays within /etc/wireguard or ~/.wireguard
- **openclaw_plugin_service.py**: Validate config_dir stays within ~/.openclaw
- **openclaw_gateway_proxy_service.py**: Validate config_dir stays within ~/.openclaw
- **wireguard_keys.py**: Validate key storage paths stay within ~/.wireguard

### 3. Add Path Traversal Tests
Create `tests/security/test_path_traversal.py` with tests for:
- `../../../etc/passwd`
- `..\\..\\..\\windows\\system32\\config\\sam`
- `./../../../etc/shadow`
- `....//....//....//etc/passwd`
- `file.txt\x00.jpg` (null byte injection)
- `.htaccess` (hidden files)

### 4. Update Security Documentation
Document secure file handling practices in security guidelines.

## Next Steps
1. ✅ Complete audit (this document)
2. ⏳ Create secure file utility module
3. ⏳ Fix all identified vulnerabilities
4. ⏳ Create comprehensive test suite
5. ⏳ Update security documentation
6. ⏳ Create PR for review

## References
- OWASP A01:2021 - Broken Access Control
- CWE-22: Path Traversal
- CWE-23: Relative Path Traversal
- CVE-2026-26329
