/**
 * DBOS Schema Migration Script
 *
 * Creates the dbos_system schema and required tables for DBOS workflow durability.
 * This must be run before starting the OpenClaw Gateway.
 *
 * Usage: npm run dbos:migrate
 */
import pg from 'pg';
import dotenv from 'dotenv';
dotenv.config();
const { Pool } = pg;
async function migrate() {
    const pool = new Pool({
        host: process.env.PGHOST,
        port: parseInt(process.env.PGPORT || '6432'),
        database: process.env.PGDATABASE,
        user: process.env.PGUSER,
        password: process.env.PGPASSWORD,
        ssl: process.env.NODE_ENV === 'production' ? { rejectUnauthorized: false } : undefined,
    });
    const client = await pool.connect();
    try {
        console.log('Starting DBOS schema migration...');
        // Create dbos_system schema
        await client.query('CREATE SCHEMA IF NOT EXISTS dbos_system;');
        console.log('✓ Created dbos_system schema');
        // Create workflow_status table
        await client.query(`
      CREATE TABLE IF NOT EXISTS dbos_system.workflow_status (
        workflow_uuid UUID PRIMARY KEY,
        status VARCHAR(50) NOT NULL,
        name VARCHAR(255) NOT NULL,
        authenticated_user VARCHAR(255),
        assumed_role VARCHAR(255),
        authenticated_roles TEXT[],
        request JSONB,
        recovery_attempts INTEGER DEFAULT 0,
        executor_id VARCHAR(255),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
      );
    `);
        console.log('✓ Created workflow_status table');
        // Create workflow_events table
        await client.query(`
      CREATE TABLE IF NOT EXISTS dbos_system.workflow_events (
        workflow_uuid UUID NOT NULL REFERENCES dbos_system.workflow_status(workflow_uuid),
        function_id INTEGER NOT NULL,
        function_name VARCHAR(255) NOT NULL,
        event_type VARCHAR(50) NOT NULL,
        event_data JSONB,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (workflow_uuid, function_id)
      );
    `);
        console.log('✓ Created workflow_events table');
        // Create operation_outputs table
        await client.query(`
      CREATE TABLE IF NOT EXISTS dbos_system.operation_outputs (
        workflow_uuid UUID NOT NULL,
        function_id INTEGER NOT NULL,
        output JSONB,
        error TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (workflow_uuid, function_id),
        FOREIGN KEY (workflow_uuid) REFERENCES dbos_system.workflow_status(workflow_uuid)
      );
    `);
        console.log('✓ Created operation_outputs table');
        // Create notifications table for workflow notifications
        await client.query(`
      CREATE TABLE IF NOT EXISTS dbos_system.notifications (
        id SERIAL PRIMARY KEY,
        workflow_uuid UUID NOT NULL REFERENCES dbos_system.workflow_status(workflow_uuid),
        topic VARCHAR(255) NOT NULL,
        message JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
      );
    `);
        console.log('✓ Created notifications table');
        // Create indexes for performance
        await client.query(`
      CREATE INDEX IF NOT EXISTS idx_workflow_status_created_at 
      ON dbos_system.workflow_status(created_at DESC);
    `);
        await client.query(`
      CREATE INDEX IF NOT EXISTS idx_workflow_status_status 
      ON dbos_system.workflow_status(status);
    `);
        await client.query(`
      CREATE INDEX IF NOT EXISTS idx_workflow_events_workflow_uuid 
      ON dbos_system.workflow_events(workflow_uuid);
    `);
        await client.query(`
      CREATE INDEX IF NOT EXISTS idx_notifications_workflow_uuid 
      ON dbos_system.notifications(workflow_uuid);
    `);
        console.log('✓ Created performance indexes');
        console.log('\n✅ DBOS schema migration completed successfully!');
        console.log('\nCreated tables:');
        console.log('  - dbos_system.workflow_status');
        console.log('  - dbos_system.workflow_events');
        console.log('  - dbos_system.operation_outputs');
        console.log('  - dbos_system.notifications');
    }
    catch (error) {
        console.error('❌ Migration failed:', error);
        throw error;
    }
    finally {
        client.release();
        await pool.end();
    }
}
// Run migration
migrate().catch((error) => {
    console.error('Fatal error during migration:', error);
    process.exit(1);
});
//# sourceMappingURL=migrate.js.map