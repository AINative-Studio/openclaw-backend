# Axios to Fetch Conversion Guide

This document shows how to convert the axios calls in `skill-installation-workflow.ts` to native `fetch()`.

## Required Imports

```typescript
import { DBOS, WorkflowContext } from '@dbos-inc/dbos-sdk';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';
const API_BASE = `${BACKEND_URL}/api/v1`;
```

## Step 1: validatePrerequisites()

### Current (Axios):
```typescript
const response = await axios.get(
  `${API_BASE}/skills/${request.skillName}/install-info`,
  { timeout: 10000 }
);
const installInfo = response.data;
```

### Converted (Fetch):
```typescript
const controller = new AbortController();
const timeoutId = setTimeout(() => controller.abort(), 10000);

const response = await fetch(
  `${API_BASE}/skills/${request.skillName}/install-info`,
  { signal: controller.signal }
);

clearTimeout(timeoutId);

if (!response.ok) {
  const errorData = await response.json().catch(() => ({ detail: response.statusText }));
  throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
}

const installInfo = await response.json();
```

## Step 2: executeInstallCommand()

### Current (Axios):
```typescript
const response = await axios.post(
  `${API_BASE}/skills/${request.skillName}/install`,
  {
    force: false,
    timeout: installTimeout,
  },
  {
    timeout: axiosTimeout,
  }
);
const result = response.data;
```

### Converted (Fetch):
```typescript
const controller = new AbortController();
const timeoutId = setTimeout(() => controller.abort(), fetchTimeout);

const response = await fetch(
  `${API_BASE}/skills/${request.skillName}/install`,
  {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      force: false,
      timeout: installTimeout,
    }),
    signal: controller.signal,
  }
);

clearTimeout(timeoutId);

if (!response.ok) {
  const errorData = await response.json().catch(() => ({ detail: response.statusText }));
  throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
}

const result = await response.json();
```

## Step 3: verifyBinary()

### Current (Axios):
```typescript
const response = await axios.get(
  `${API_BASE}/skills/${skillName}/installation-status`,
  { timeout: 10000 }
);
const status = response.data;
```

### Converted (Fetch):
```typescript
const controller = new AbortController();
const timeoutId = setTimeout(() => controller.abort(), 10000);

const response = await fetch(
  `${API_BASE}/skills/${skillName}/installation-status`,
  { signal: controller.signal }
);

clearTimeout(timeoutId);

if (!response.ok) {
  const errorData = await response.json().catch(() => ({ detail: response.statusText }));
  throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
}

const status = await response.json();
```

## Error Handling Pattern

### Axios pattern:
```typescript
catch (error: any) {
  const errorMsg = error.response?.data?.detail || error.message || 'Unknown error';
  ctx.logger.error(`Operation failed: ${errorMsg}`);
  return { success: false, error: errorMsg };
}
```

### Fetch pattern:
```typescript
catch (error: any) {
  const errorMsg = error.message || 'Unknown error';
  ctx.logger.error(`Operation failed: ${errorMsg}`);
  return { success: false, error: errorMsg };
}
```

Note: With fetch, HTTP errors are handled before the catch block (in the `if (!response.ok)` check),
so `error.message` directly contains the error string.

## Complete Converted Methods

### validatePrerequisites() - Complete
```typescript
@DBOS.step()
static async validatePrerequisites(
  ctx: WorkflowContext,
  request: SkillInstallRequest
): Promise<PrerequisiteValidationResult> {
  try {
    ctx.logger.info(`Validating prerequisites for skill: ${request.skillName}`);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000);

    const response = await fetch(
      `${API_BASE}/skills/${request.skillName}/install-info`,
      { signal: controller.signal }
    );

    clearTimeout(timeoutId);

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
    }

    const installInfo = await response.json();

    if (!installInfo.installable) {
      const error = `Skill '${request.skillName}' is not auto-installable (method: ${installInfo.method}). ${
        installInfo.docs ? `See docs: ${installInfo.docs}` : ''
      }`;
      ctx.logger.warn(error);
      return { success: false, error };
    }

    if (installInfo.method !== request.method) {
      const error = `Method mismatch: requested '${request.method}' but skill uses '${installInfo.method}'`;
      ctx.logger.warn(error);
      return { success: false, error };
    }

    ctx.logger.info(
      `Prerequisites validated: ${request.skillName} (${installInfo.method}, package: ${installInfo.package || 'N/A'})`
    );

    return { success: true };
  } catch (error: any) {
    const errorMsg = error.message || 'Unknown error';
    ctx.logger.error(`Prerequisites validation failed: ${errorMsg}`);
    return { success: false, error: `Prerequisites validation failed: ${errorMsg}` };
  }
}
```

### executeInstallCommand() - Complete
```typescript
@DBOS.step()
static async executeInstallCommand(
  ctx: WorkflowContext,
  request: SkillInstallRequest
): Promise<any> {
  try {
    ctx.logger.info(`Starting installation of ${request.skillName} via ${request.method}`);

    const installTimeout = 300;
    const fetchTimeout = (installTimeout + 10) * 1000;

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), fetchTimeout);

    const response = await fetch(
      `${API_BASE}/skills/${request.skillName}/install`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ force: false, timeout: installTimeout }),
        signal: controller.signal,
      }
    );

    clearTimeout(timeoutId);

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
    }

    const result = await response.json();

    if (!result.success) {
      const error = result.message || 'Installation failed with no error message';
      ctx.logger.error(`Installation failed: ${error}`);
      throw new Error(error);
    }

    ctx.logger.info(
      `Installation completed successfully: ${request.skillName} (${result.method}, package: ${result.package || 'N/A'})`
    );

    if (result.logs && result.logs.length > 0) {
      ctx.logger.debug(`Installation logs: ${result.logs.join('\n')}`);
    }

    return result;
  } catch (error: any) {
    const errorMsg = error.message || 'Unknown error';
    ctx.logger.error(`Installation command failed: ${errorMsg}`);
    throw new Error(`Installation failed: ${errorMsg}`);
  }
}
```

### verifyBinary() - Complete
```typescript
@DBOS.step()
static async verifyBinary(
  ctx: WorkflowContext,
  skillName: string
): Promise<BinaryVerificationResult> {
  try {
    ctx.logger.info(`Verifying binary installation for: ${skillName}`);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000);

    const response = await fetch(
      `${API_BASE}/skills/${skillName}/installation-status`,
      { signal: controller.signal }
    );

    clearTimeout(timeoutId);

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
    }

    const status = await response.json();

    if (status.is_installed && status.binary_path) {
      ctx.logger.info(`Binary verified: ${status.binary_path}`);
      return { success: true, binaryPath: status.binary_path };
    } else {
      const error = `Binary not found in PATH for skill: ${skillName}`;
      ctx.logger.error(error);
      return { success: false, error };
    }
  } catch (error: any) {
    const errorMsg = error.message || 'Unknown error';
    ctx.logger.error(`Binary verification failed: ${errorMsg}`);
    return { success: false, error: `Binary verification failed: ${errorMsg}` };
  }
}
```
