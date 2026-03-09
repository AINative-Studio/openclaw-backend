/**
 * Skill Installation Workflow
 *
 * DBOS durable workflow for installing skills (CLI tools, packages) via npm or brew
 * with automatic rollback on failure and crash recovery.
 *
 * Phase 4: Skill Installation
 * Agent 2: Installation Workflow Core Developer
 */

import { DBOS } from '@dbos-inc/dbos-sdk';
import axios from 'axios';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';
const API_BASE = `${BACKEND_URL}/api/v1`;

// ============================================================================
// INTERFACES
// ============================================================================

/**
 * Skill installation request
 */
export interface SkillInstallRequest {
  /** Skill name (e.g., 'ripgrep', 'jq') */
  skillName: string;
  /** Installation method: npm or brew */
  method: 'npm' | 'brew';
  /** Optional: Agent ID requesting the installation */
  agentId?: string;
  /** Optional: Package name (if different from skill name) */
  packageName?: string;
}

/**
 * Skill installation result
 */
export interface SkillInstallResult {
  /** Whether installation succeeded */
  success: boolean;
  /** Skill name */
  skillName: string;
  /** When the skill was installed */
  installedAt?: Date;
  /** Path to the installed binary */
  binaryPath?: string;
  /** Error message if installation failed */
  error?: string;
  /** Installation method used */
  method?: 'npm' | 'brew';
}

/**
 * Installation history record (stored in database)
 */
interface InstallationHistoryRecord {
  /** Skill name */
  skillName: string;
  /** Agent ID (if installation was agent-specific) */
  agentId?: string;
  /** Installation status */
  status: 'STARTED' | 'COMPLETED' | 'FAILED' | 'ROLLED_BACK';
  /** Installation method */
  method: string;
  /** Package name (may differ from skill name) */
  packageName?: string;
  /** Path to installed binary */
  binaryPath?: string;
  /** When installation started */
  startedAt: Date;
  /** When installation completed */
  completedAt?: Date;
  /** Error message if failed */
  errorMessage?: string;
}

/**
 * Prerequisite validation result
 */
interface PrerequisiteValidationResult {
  /** Whether validation passed */
  success: boolean;
  /** Error message if validation failed */
  error?: string;
}

/**
 * Binary verification result
 */
interface BinaryVerificationResult {
  /** Whether binary was found and is executable */
  success: boolean;
  /** Path to the verified binary */
  binaryPath?: string;
  /** Error message if verification failed */
  error?: string;
}

// ============================================================================
// SKILL INSTALLATION WORKFLOW CLASS
// ============================================================================

/**
 * Skill Installation Workflow
 *
 * Implements durable workflows for skill installation with:
 * - Pre-flight validation (package manager availability)
 * - Installation execution (npm/brew)
 * - Binary verification (existence + executability)
 * - Automatic rollback on failure
 * - Crash recovery (resume from last completed step)
 */
export class SkillInstallationWorkflow {
  // ============================================================================
  // MAIN WORKFLOW
  // ============================================================================

  /**
   * Durable skill installation with rollback
   *
   * Steps:
   * 1. Validate prerequisites (package manager available)
   * 2. Record installation start in database
   * 3. Execute installation command (npm/brew)
   * 4. Verify binary exists and is executable
   * 5. Record success in database
   *
   * On failure: Rollback (uninstall package)
   * On crash: Resume from last completed step
   *
   * @param request - Installation request details
   * @returns Installation result with success status
   */
  @DBOS.workflow()
  static async installSkill(request: SkillInstallRequest): Promise<SkillInstallResult> {
    DBOS.logger.info(`Starting skill installation workflow: ${request.skillName} via ${request.method}`);

    try {
      // Step 1: Pre-flight validation (Agent 3 will implement)
      const validated = await SkillInstallationWorkflow.validatePrerequisites(request);

      if (!validated.success) {
        DBOS.logger.error(`Prerequisite validation failed: ${validated.error}`);
        return {
          success: false,
          skillName: request.skillName,
          error: validated.error,
          method: request.method
        };
      }

      // Step 2: Record installation attempt (Agent 4 will implement)
      await SkillInstallationWorkflow.recordInstallationStart(request);

      // Step 3: Execute installation (Agent 3 will implement)
      let installResult;
      try {
        installResult = await SkillInstallationWorkflow.executeInstallCommand(request);
      } catch (error: any) {
        const errorMessage = error instanceof Error ? error.message : 'Unknown installation error';
        DBOS.logger.error(`Installation failed: ${errorMessage}`, error);

        // Rollback on failure (Agent 4 will implement)
        await SkillInstallationWorkflow.rollbackInstallation(request);

        // Record failure in database
        await SkillInstallationWorkflow.recordInstallationFailure(request, errorMessage);

        return {
          success: false,
          skillName: request.skillName,
          error: errorMessage,
          method: request.method
        };
      }

      // Step 4: Verify binary (Agent 3 will implement)
      const verified = await SkillInstallationWorkflow.verifyBinary(request.skillName);

      if (!verified.success) {
        DBOS.logger.error(`Binary verification failed: ${verified.error}`);

        // Rollback - binary not found or not executable
        await SkillInstallationWorkflow.rollbackInstallation(request);

        // Record failure
        await SkillInstallationWorkflow.recordInstallationFailure(
          request,
          verified.error || 'Binary verification failed'
        );

        return {
          success: false,
          skillName: request.skillName,
          error: verified.error || 'Binary verification failed',
          method: request.method
        };
      }

      // Step 5: Record success (Agent 4 will implement)
      await SkillInstallationWorkflow.recordInstallationSuccess({
        skillName: request.skillName,
        binaryPath: verified.binaryPath,
        installedAt: new Date(),
        method: request.method
      });

      const result: SkillInstallResult = {
        success: true,
        skillName: request.skillName,
        installedAt: new Date(),
        binaryPath: verified.binaryPath,
        method: request.method
      };

      DBOS.logger.info(`Skill installation workflow completed: ${request.skillName}`);
      return result;
    } catch (error: any) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown workflow error';
      DBOS.logger.error(`Skill installation workflow failed: ${errorMessage}`, error);

      // Ensure failure is recorded even if rollback fails
      try {
        await SkillInstallationWorkflow.recordInstallationFailure(request, errorMessage);
      } catch (recordError) {
        DBOS.logger.error('Failed to record installation failure', recordError);
      }

      return {
        success: false,
        skillName: request.skillName,
        error: errorMessage,
        method: request.method
      };
    }
  }

  // ============================================================================
  // STEP STUBS (TO BE IMPLEMENTED BY OTHER AGENTS)
  // ============================================================================

  /**
   * Validate installation prerequisites
   *
   * Checks if the skill is installable and verifies the installation method.
   * Calls Backend API: GET /api/v1/skills/{skillName}/install-info
   *
   * @param request - Installation request
   * @returns Validation result
   */
  @DBOS.step()
  static async validatePrerequisites(
    request: SkillInstallRequest
  ): Promise<PrerequisiteValidationResult> {
    try {
      DBOS.logger.info(`Validating prerequisites for skill: ${request.skillName}`);

      // Call Backend API to get skill installation info
      const response = await axios.get(
        `${API_BASE}/skills/${request.skillName}/install-info`,
        { timeout: 10000 } // 10 second timeout for metadata lookup
      );

      const installInfo = response.data;

      // Check if skill is auto-installable
      if (!installInfo.installable) {
        const error = `Skill '${request.skillName}' is not auto-installable (method: ${installInfo.method}). ${
          installInfo.docs ? `See docs: ${installInfo.docs}` : ''
        }`;
        DBOS.logger.warn(error);
        return {
          success: false,
          error,
        };
      }

      // Verify the method matches what was requested
      if (installInfo.method !== request.method) {
        const error = `Method mismatch: requested '${request.method}' but skill uses '${installInfo.method}'`;
        DBOS.logger.warn(error);
        return {
          success: false,
          error,
        };
      }

      DBOS.logger.info(
        `Prerequisites validated: ${request.skillName} (${installInfo.method}, package: ${installInfo.package || 'N/A'})`
      );

      return {
        success: true,
      };
    } catch (error: any) {
      const errorMsg = error.response?.data?.detail || error.message || 'Unknown error';
      DBOS.logger.error(`Prerequisites validation failed: ${errorMsg}`);

      return {
        success: false,
        error: `Prerequisites validation failed: ${errorMsg}`,
      };
    }
  }

  /**
   * Execute installation command
   *
   * Calls the Backend API to install the skill using the appropriate package manager.
   * Calls Backend API: POST /api/v1/skills/{skillName}/install
   *
   * @param request - Installation request
   * @returns Installation metadata
   */
  @DBOS.step()
  static async executeInstallCommand(request: SkillInstallRequest): Promise<any> {
    try {
      DBOS.logger.info(`Starting installation of ${request.skillName} via ${request.method}`);

      // Call Backend API to execute installation
      const installTimeout = 300; // Default 5 minutes (Backend enforces 30-600s range)
      const axiosTimeout = (installTimeout + 10) * 1000; // Add 10s buffer for HTTP timeout

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

      if (!result.success) {
        const error = result.message || 'Installation failed with no error message';
        DBOS.logger.error(`Installation failed: ${error}`);
        throw new Error(error);
      }

      DBOS.logger.info(
        `Installation completed successfully: ${request.skillName} (${result.method}, package: ${result.package || 'N/A'})`
      );

      if (result.logs && result.logs.length > 0) {
        DBOS.logger.debug(`Installation logs: ${result.logs.join('\n')}`);
      }

      return result;
    } catch (error: any) {
      const errorMsg = error.response?.data?.detail || error.message || 'Unknown error';
      DBOS.logger.error(`Installation command failed: ${errorMsg}`);

      // Re-throw to mark workflow as failed
      throw new Error(`Installation failed: ${errorMsg}`);
    }
  }

  /**
   * Verify installed binary
   *
   * Checks if the installed binary is accessible in PATH.
   * Calls Backend API: GET /api/v1/skills/{skillName}/installation-status
   *
   * @param skillName - Name of skill to verify
   * @returns Verification result with binary path
   */
  @DBOS.step()
  static async verifyBinary(skillName: string): Promise<BinaryVerificationResult> {
    try {
      DBOS.logger.info(`Verifying binary installation for: ${skillName}`);

      // Call Backend API to check installation status
      const response = await axios.get(
        `${API_BASE}/skills/${skillName}/installation-status`,
        { timeout: 10000 } // 10 second timeout for binary check
      );

      const status = response.data;

      if (status.is_installed && status.binary_path) {
        DBOS.logger.info(`Binary verified: ${status.binary_path}`);
        return {
          success: true,
          binaryPath: status.binary_path,
        };
      } else {
        const error = `Binary not found in PATH for skill: ${skillName}`;
        DBOS.logger.error(error);
        return {
          success: false,
          error,
        };
      }
    } catch (error: any) {
      const errorMsg = error.response?.data?.detail || error.message || 'Unknown error';
      DBOS.logger.error(`Binary verification failed: ${errorMsg}`);

      return {
        success: false,
        error: `Binary verification failed: ${errorMsg}`,
      };
    }
  }

  /**
   * Record installation start in database
   *
   * Agent 4 (Database Operations) will implement this step to:
   * - Insert record into skill_installations table
   * - Set status to 'STARTED'
   * - Record workflow UUID for crash recovery
   * - Use idempotent upsert (ON CONFLICT DO UPDATE)
   *
   * @param request - Installation request
   */
  @DBOS.step()
  static async recordInstallationStart(request: SkillInstallRequest): Promise<void> {
    try {
      DBOS.logger.info(`[SkillInstallation] Recording installation start via backend API: ${request.skillName}`);

      // Call backend API to record audit log
      // Gateway should not write directly to app database - that's Backend's responsibility
      const response = await axios.post(
        `${BACKEND_URL}/api/v1/skills/${request.skillName}/installation/audit`,
        {
          status: 'STARTED',
          method: request.method,
          agent_id: request.agentId,
          package_name: request.packageName,
        },
        { timeout: 5000 }
      );

      DBOS.logger.info(`[SkillInstallation] ✓ Recorded installation start: ${request.skillName}`);
    } catch (error: any) {
      DBOS.logger.warn(`[SkillInstallation] Failed to record installation start (non-fatal): ${error.message}`);
      // Don't throw - database logging is non-critical
    }
  }

  /**
   * Record successful installation in database
   *
   * Agent 4 (Database Operations) will implement this step to:
   * - Update skill_installations record
   * - Set status to 'COMPLETED'
   * - Record binary path and completion timestamp
   * - Mark as available for use
   *
   * @param data - Success metadata (skill name, binary path, timestamp)
   */
  @DBOS.step()
  static async recordInstallationSuccess(data: any): Promise<void> {
    try {
      DBOS.logger.info(`[SkillInstallation] Recording installation success via backend API: ${data.skillName}`);

      // Call backend API to update audit log
      await axios.post(
        `${BACKEND_URL}/api/v1/skills/${data.skillName}/installation/audit`,
        {
          status: 'COMPLETED',
          method: data.method || 'unknown',
          binary_path: data.binaryPath || null,
        },
        { timeout: 5000 }
      );

      DBOS.logger.info(`[SkillInstallation] ✓ Recorded installation success: ${data.skillName}`);
    } catch (error: any) {
      DBOS.logger.warn(`[SkillInstallation] Failed to record installation success (non-fatal): ${error.message}`);
      // Don't throw - database logging is non-critical
    }
  }

  /**
   * Record installation failure in database
   *
   * Agent 4 (Database Operations) will implement this step to:
   * - Update skill_installations record
   * - Set status to 'FAILED'
   * - Record error message and failure timestamp
   * - Increment retry count (if applicable)
   *
   * @param request - Installation request
   * @param errorMessage - Failure reason
   */
  @DBOS.step()
  static async recordInstallationFailure(
    request: SkillInstallRequest,
    errorMessage: string
  ): Promise<void> {
    try {
      DBOS.logger.info(`[SkillInstallation] Recording installation failure via backend API: ${request.skillName}`);

      // Call backend API to update audit log
      await axios.post(
        `${BACKEND_URL}/api/v1/skills/${request.skillName}/installation/audit`,
        {
          status: 'FAILED',
          method: request.method,
          error_message: errorMessage,
        },
        { timeout: 5000 }
      );

      DBOS.logger.error(`[SkillInstallation] ✓ Recorded installation failure: ${request.skillName} - ${errorMessage}`);
    } catch (error: any) {
      DBOS.logger.warn(`[SkillInstallation] Failed to record installation failure (non-fatal): ${error.message}`);
      // Don't throw - database logging is non-critical
    }
  }

  /**
   * Rollback installation (uninstall package)
   *
   * Agent 4 (Database Operations) will implement this step to:
   * - Execute uninstall command (npm uninstall -g / brew uninstall)
   * - Update database status to 'ROLLED_BACK'
   * - Clean up any temporary files
   * - Ensure idempotent behavior (safe to retry)
   *
   * @param request - Installation request
   */
  @DBOS.step()
  static async rollbackInstallation(request: SkillInstallRequest): Promise<void> {
    DBOS.logger.warn(`[SkillInstallation] Rolling back installation: ${request.skillName}`);

    // Try to uninstall the package
    try {
      const response = await axios.delete(
        `${BACKEND_URL}/api/v1/skills/${request.skillName}/install`,
        { timeout: 60000 }
      );

      DBOS.logger.info(`[SkillInstallation] Rollback uninstall completed: ${request.skillName}`);
    } catch (error: any) {
      // Uninstall failure is non-fatal during rollback
      DBOS.logger.warn(`[SkillInstallation] Rollback uninstall failed (non-fatal): ${error.message}`);
    }

    // Update database status to ROLLED_BACK via backend API
    try {
      await axios.post(
        `${BACKEND_URL}/api/v1/skills/${request.skillName}/installation/audit`,
        {
          status: 'ROLLED_BACK',
          method: request.method,
          error_message: 'Installation rolled back due to verification failure',
        },
        { timeout: 5000 }
      );

      DBOS.logger.info(`[SkillInstallation] ✓ Recorded rollback status: ${request.skillName}`);
    } catch (error: any) {
      DBOS.logger.warn(`[SkillInstallation] Failed to record rollback status (non-fatal): ${error.message}`);
      // Don't throw - database logging is non-critical
    }
  }

  // ============================================================================
  // QUERY OPERATIONS (TO BE IMPLEMENTED)
  // ============================================================================

  /**
   * Get installation status
   *
   * Query the current status of a skill installation workflow.
   * Useful for monitoring and debugging.
   *
   * @param skillName - Skill to query
   * @returns Installation history record
   */
  @DBOS.step()
  static async getInstallationStatus(
    skillName: string
  ): Promise<InstallationHistoryRecord | null> {
    // Agent 4 will implement
    DBOS.logger.info(`[STUB] Querying installation status for ${skillName}`);
    return null;
  }

  /**
   * List all installed skills
   *
   * Query all successfully installed skills.
   *
   * @returns Array of installation records
   */
  @DBOS.step()
  static async listInstalledSkills(): Promise<InstallationHistoryRecord[]> {
    // Agent 4 will implement
    DBOS.logger.info(`[STUB] Listing all installed skills`);
    return [];
  }
}
