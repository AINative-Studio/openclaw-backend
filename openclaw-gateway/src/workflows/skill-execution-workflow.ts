import { DBOS } from '@dbos-inc/dbos-sdk';
import { randomUUID } from 'crypto';
import axios from 'axios';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

// Interfaces
export interface SkillExecutionRequest {
  skillName: string;
  agentId: string;
  parameters: Record<string, any>;
  timeoutSeconds?: number;
}

export interface SkillExecutionResult {
  success: boolean;
  skillName: string;
  output?: string;
  error?: string;
  executionTimeMs: number;
}

interface ExecutionHistoryRecord {
  executionId: string;
  skillName: string;
  agentId: string;
  status: 'RUNNING' | 'COMPLETED' | 'FAILED' | 'TIMEOUT';
  parameters: Record<string, any>;
  output?: string;
  errorMessage?: string;
  executionTimeMs?: number;
  startedAt: Date;
  completedAt?: Date;
}

// Main Workflow Class
export class SkillExecutionWorkflow {
  /**
   * Durable skill execution with retry
   *
   * Steps:
   * 1. Validate skill is installed and accessible
   * 2. Validate agent has permission to use skill
   * 3. Record execution start
   * 4. Execute skill command
   * 5. Capture output/errors
   * 6. Record execution result
   *
   * On crash: Resume and complete execution
   * On timeout: Retry with backoff
   */
  @DBOS.workflow()
  static async executeSkill(
    request: SkillExecutionRequest
  ): Promise<SkillExecutionResult> {
    const startTime = Date.now();
    DBOS.logger.info(`Starting skill execution: ${request.skillName} for agent ${request.agentId}`);

    // Step 1: Validate skill is installed
    const installed = await SkillExecutionWorkflow.validateSkillInstalled(request.skillName);
    if (!installed.success) {
      return {
        success: false,
        skillName: request.skillName,
        error: `Skill '${request.skillName}' not installed`,
        executionTimeMs: Date.now() - startTime
      };
    }

    // Step 2: Check agent permissions
    const authorized = await SkillExecutionWorkflow.checkAgentPermission(request);
    if (!authorized.success) {
      return {
        success: false,
        skillName: request.skillName,
        error: `Agent ${request.agentId} not authorized for skill '${request.skillName}'`,
        executionTimeMs: Date.now() - startTime
      };
    }

    // Step 3: Record execution start
    const executionId = await SkillExecutionWorkflow.recordExecutionStart(request);

    // Step 4: Execute skill
    let result;
    try {
      result = await SkillExecutionWorkflow.runSkillCommand({
        skillName: request.skillName,
        parameters: request.parameters,
        timeoutSeconds: request.timeoutSeconds || 60
      });
    } catch (error: any) {
      // Record failure
      await SkillExecutionWorkflow.recordExecutionFailure({
        executionId,
        error: error.message
      });
      throw error;
    }

    // Step 5: Record success
    await SkillExecutionWorkflow.recordExecutionSuccess({
      executionId,
      output: result.output,
      executionTimeMs: Date.now() - startTime
    });

    return {
      success: true,
      skillName: request.skillName,
      output: result.output,
      executionTimeMs: Date.now() - startTime
    };
  }

  /**
   * Step 1: Validate that skill binary is installed
   *
   * Calls Backend API: GET /api/v1/skills/{skillName}/installation-status
   */
  @DBOS.step()
  static async validateSkillInstalled(
    skillName: string
  ): Promise<{success: boolean, error?: string}> {
    DBOS.logger.info(`Validating skill installation: ${skillName}`);

    try {
      const response = await axios.get(
        `${BACKEND_URL}/api/v1/skills/${skillName}/installation-status`,
        {
          timeout: 10000,
          validateStatus: (status) => status < 500, // Don't throw on 4xx
        }
      );

      if (response.status === 404) {
        return {
          success: false,
          error: `Skill '${skillName}' not found in registry`,
        };
      }

      const data = response.data;

      if (data.is_installed) {
        DBOS.logger.info(`Skill '${skillName}' is installed at: ${data.binary_path || 'PATH'}`);
        return { success: true };
      } else {
        return {
          success: false,
          error: `Skill '${skillName}' not installed. Install it first using the Installation API.`,
        };
      }
    } catch (error: any) {
      DBOS.logger.error(`Error validating skill installation: ${error.message}`);
      return {
        success: false,
        error: `Failed to validate skill installation: ${error.message}`,
      };
    }
  }

  /**
   * Step 2: Check if agent has permission to use this skill
   *
   * Calls Backend API: GET /api/v1/agents/{agentId}/skills/{skillName}
   */
  @DBOS.step()
  static async checkAgentPermission(
    
    request: SkillExecutionRequest
  ): Promise<{success: boolean, error?: string}> {
    // If no agentId, allow execution (system-level skill execution)
    if (!request.agentId) {
      DBOS.logger.info('No agentId provided, skipping permission check');
      return { success: true };
    }

    DBOS.logger.info(`Checking agent permission: agent=${request.agentId}, skill=${request.skillName}`);

    try {
      const response = await axios.get(
        `${BACKEND_URL}/api/v1/agents/${request.agentId}/skills/${request.skillName}`,
        {
          timeout: 10000,
          validateStatus: (status) => status < 500,
        }
      );

      if (response.status === 404) {
        // Skill config doesn't exist - assume allowed for now
        DBOS.logger.warn(
          `Agent skill config not found for agent ${request.agentId}, skill ${request.skillName} - assuming allowed`
        );
        return { success: true };
      }

      const config = response.data;

      if (config.enabled) {
        DBOS.logger.info(`Agent ${request.agentId} has permission to use skill '${request.skillName}'`);
        return { success: true };
      } else {
        return {
          success: false,
          error: `Skill '${request.skillName}' is disabled for agent ${request.agentId}`,
        };
      }
    } catch (error: any) {
      // On error, log warning but allow execution (fail-open for now)
      DBOS.logger.warn(`Error checking agent permission: ${error.message} - allowing execution`);
      return { success: true };
    }
  }

  /**
   * Step 3: Execute the skill command
   *
   * TODO: This is a stub implementation. Real implementation needs to:
   * 1. Call OpenClaw CLI: openclaw skills exec <skillName> -- <args>
   * 2. Parse parameters into CLI arguments
   * 3. Capture stdout/stderr
   * 4. Handle timeouts
   * 5. Handle execution errors
   *
   * For now, returns stub output.
   */
  @DBOS.step()
  static async runSkillCommand(
    
    params: { skillName: string; parameters: Record<string, any>; timeoutSeconds: number }
  ): Promise<{output: string}> {
    DBOS.logger.info(
      `Executing skill: ${params.skillName} with params: ${JSON.stringify(params.parameters)}`
    );

    // TODO: Replace with actual OpenClaw CLI execution
    // Expected implementation:
    //
    // const { spawn } = require('child_process');
    // const args = ['skills', 'exec', params.skillName, '--'];
    //
    // // Convert parameters to CLI arguments
    // for (const [key, value] of Object.entries(params.parameters)) {
    //   args.push(`--${key}`, String(value));
    // }
    //
    // const process = spawn('openclaw', args, {
    //   timeout: params.timeoutSeconds * 1000,
    //   env: { ...process.env },
    // });
    //
    // let stdout = '';
    // let stderr = '';
    //
    // process.stdout.on('data', (data) => { stdout += data; });
    // process.stderr.on('data', (data) => { stderr += data; });
    //
    // await new Promise((resolve, reject) => {
    //   process.on('close', (code) => {
    //     if (code === 0) resolve(stdout);
    //     else reject(new Error(`Skill exited with code ${code}: ${stderr}`));
    //   });
    //   process.on('error', reject);
    // });

    DBOS.logger.warn('Using stub skill execution - real OpenClaw CLI integration pending');

    // Return stub output
    return {
      output: JSON.stringify({
        status: 'success',
        message: `Executed ${params.skillName} (stub implementation)`,
        parameters: params.parameters,
        note: 'This is a placeholder - real skill execution not yet implemented',
      }, null, 2),
    };
  }

  /**
   * Step 4: Record execution start in database
   *
   * Inserts new record into skill_execution_history with RUNNING status
   */
  @DBOS.step()
  static async recordExecutionStart(
    
    request: SkillExecutionRequest
  ): Promise<string> {
    const executionId = randomUUID();

    DBOS.logger.info(`Recording execution start: executionId=${executionId}, skill=${request.skillName}`);

    try {
      // Access knex client (configured as app_db_client in dbos-config.yaml)
      const knex = (DBOS as any).knexClient;
      if (!knex) {
        DBOS.logger.error('knexClient not available - cannot record execution start');
        throw new Error('Database client not available');
      }

      await knex.raw(
        `INSERT INTO skill_execution_history
         (execution_id, skill_name, agent_id, status, parameters, started_at)
         VALUES (?, ?, ?, 'RUNNING', ?, NOW())`,
        [
          executionId,
          request.skillName,
          request.agentId || null,
          JSON.stringify(request.parameters),
        ]
      );

      DBOS.logger.info(`Execution start recorded: ${executionId}`);
      return executionId;
    } catch (error: any) {
      DBOS.logger.error(`Failed to record execution start: ${error.message}`);
      throw error;
    }
  }

  /**
   * Step 5: Record successful execution completion
   *
   * Updates skill_execution_history with COMPLETED status, output, and timing
   */
  @DBOS.step()
  static async recordExecutionSuccess(
    
    data: { executionId: string; output: string; executionTimeMs: number }
  ): Promise<void> {
    DBOS.logger.info(`Recording execution success: executionId=${data.executionId}`);

    try {
      const knex = (DBOS as any).knexClient;
      if (!knex) {
        DBOS.logger.error('knexClient not available - cannot record execution success');
        throw new Error('Database client not available');
      }

      await knex.raw(
        `UPDATE skill_execution_history
         SET status = 'COMPLETED',
             output = ?,
             execution_time_ms = ?,
             completed_at = NOW(),
             updated_at = NOW()
         WHERE execution_id = ?`,
        [data.output, data.executionTimeMs, data.executionId]
      );

      DBOS.logger.info(`Execution success recorded: ${data.executionId}`);
    } catch (error: any) {
      DBOS.logger.error(`Failed to record execution success: ${error.message}`);
      throw error;
    }
  }

  /**
   * Step 6: Record execution failure
   *
   * Updates skill_execution_history with FAILED status and error message
   */
  @DBOS.step()
  static async recordExecutionFailure(
    
    data: { executionId: string; error: string }
  ): Promise<void> {
    DBOS.logger.error(`Recording execution failure: executionId=${data.executionId}, error=${data.error}`);

    try {
      const knex = (DBOS as any).knexClient;
      if (!knex) {
        DBOS.logger.error('knexClient not available - cannot record execution failure');
        throw new Error('Database client not available');
      }

      await knex.raw(
        `UPDATE skill_execution_history
         SET status = 'FAILED',
             error_message = ?,
             completed_at = NOW(),
             updated_at = NOW()
         WHERE execution_id = ?`,
        [data.error, data.executionId]
      );

      DBOS.logger.error(`Execution failure recorded: ${data.executionId} - ${data.error}`);
    } catch (error: any) {
      DBOS.logger.error(`Failed to record execution failure: ${error.message}`);
      throw error;
    }
  }
}
