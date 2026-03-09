/**
 * OpenClaw Gateway Configuration Validator
 *
 * Validates that port configuration is consistent across:
 * - .env file (PORT environment variable)
 * - dbos-config.yaml (runtimeConfig.port)
 *
 * This prevents Issue #97 from recurring.
 *
 * Usage:
 *   node validate-config.js
 *
 * Exit codes:
 *   0 - Configuration valid
 *   1 - Configuration invalid (prints errors to stderr)
 */

import fs from 'fs';
import yaml from 'yaml';
import dotenv from 'dotenv';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Expected port (canonical value)
const EXPECTED_PORT = 18789;

// File paths
const ENV_FILE = path.join(__dirname, '.env');
const DBOS_CONFIG_FILE = path.join(__dirname, 'dbos-config.yaml');

/**
 * Validate configuration files
 *
 * @returns {Object} { valid: boolean, errors: string[] }
 */
function validateConfiguration() {
    const errors = [];

    // Check .env file
    if (!fs.existsSync(ENV_FILE)) {
        errors.push(`.env file not found at ${ENV_FILE}`);
    } else {
        const envConfig = dotenv.parse(fs.readFileSync(ENV_FILE));

        if (!envConfig.PORT) {
            errors.push('.env file missing PORT variable');
        } else {
            const envPort = parseInt(envConfig.PORT);
            if (envPort !== EXPECTED_PORT) {
                errors.push(
                    `PORT mismatch in .env: expected ${EXPECTED_PORT}, got ${envPort}`
                );
            }
        }
    }

    // Check dbos-config.yaml
    if (!fs.existsSync(DBOS_CONFIG_FILE)) {
        errors.push(`dbos-config.yaml not found at ${DBOS_CONFIG_FILE}`);
    } else {
        const yamlContent = fs.readFileSync(DBOS_CONFIG_FILE, 'utf8');
        const dbosConfig = yaml.parse(yamlContent);

        if (!dbosConfig.runtimeConfig) {
            errors.push('dbos-config.yaml missing runtimeConfig section');
        } else if (!dbosConfig.runtimeConfig.port) {
            errors.push('dbos-config.yaml missing runtimeConfig.port');
        } else {
            const dbosPort = dbosConfig.runtimeConfig.port;
            if (dbosPort !== EXPECTED_PORT) {
                errors.push(
                    `PORT mismatch in dbos-config.yaml: expected ${EXPECTED_PORT}, got ${dbosPort}`
                );
            }
        }
    }

    return {
        valid: errors.length === 0,
        errors
    };
}

// Run validation
const result = validateConfiguration();

if (result.valid) {
    console.log('✓ Gateway port configuration is valid');
    console.log(`  PORT=${EXPECTED_PORT} in both .env and dbos-config.yaml`);
    process.exit(0);
} else {
    console.error('✗ Gateway port configuration is INVALID:');
    result.errors.forEach(error => {
        console.error(`  - ${error}`);
    });
    console.error('');
    console.error(`Expected: PORT=${EXPECTED_PORT} in both .env and dbos-config.yaml`);
    process.exit(1);
}
