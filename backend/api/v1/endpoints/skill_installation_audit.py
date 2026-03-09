"""
Skill Installation Audit API

Endpoints for recording skill installation history and audit logs.
Called by the OpenClaw Gateway during skill installation workflows.
"""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

from backend.db.base import get_db

router = APIRouter()


class SkillInstallationAuditRequest(BaseModel):
    """Request to record skill installation audit event"""
    status: str = Field(..., description="Installation status: STARTED, COMPLETED, FAILED, ROLLED_BACK")
    method: str = Field(..., description="Installation method: npm, brew, manual")
    agent_id: Optional[str] = Field(None, description="Agent ID if installation is agent-specific")
    package_name: Optional[str] = Field(None, description="Package name (e.g., @instinctx_dev/neuro-skill-blogwatcher)")
    binary_path: Optional[str] = Field(None, description="Path to installed binary (for COMPLETED status)")
    error_message: Optional[str] = Field(None, description="Error message (for FAILED status)")


class SkillInstallationAuditResponse(BaseModel):
    """Response from audit logging"""
    success: bool
    record_id: str
    message: str


@router.post(
    "/skills/{skill_name}/installation/audit",
    response_model=SkillInstallationAuditResponse,
    summary="Record skill installation audit event",
    description="Records skill installation events (STARTED, COMPLETED, FAILED, ROLLED_BACK) to audit trail"
)
def record_skill_installation_audit(
    skill_name: str,
    request: SkillInstallationAuditRequest,
    db: Session = Depends(get_db)
):
    """
    Record skill installation audit event.

    Called by OpenClaw Gateway during skill installation workflows to maintain
    an audit trail of all installation attempts, successes, and failures.

    **Status Values:**
    - STARTED: Installation workflow has begun
    - COMPLETED: Installation succeeded and binary verified
    - FAILED: Installation failed with error
    - ROLLED_BACK: Installation was rolled back after failure

    **Flow:**
    1. Gateway starts installation → POST with status=STARTED
    2. Installation succeeds → POST with status=COMPLETED + binary_path
    3. Installation fails → POST with status=FAILED + error_message
    4. Rollback occurs → POST with status=ROLLED_BACK
    """
    try:
        # Validate status
        valid_statuses = {'STARTED', 'COMPLETED', 'FAILED', 'ROLLED_BACK'}
        if request.status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status '{request.status}'. Must be one of: {', '.join(valid_statuses)}"
            )

        # For STARTED status: Create new record
        if request.status == 'STARTED':
            from sqlalchemy import text
            result = db.execute(
                text("""
                INSERT INTO skill_installation_history
                (skill_name, agent_id, status, method, package_name, started_at, created_at)
                VALUES (:skill_name, :agent_id, :status, :method, :package_name, NOW(), NOW())
                RETURNING id
                """),
                {
                    'skill_name': skill_name,
                    'agent_id': request.agent_id,
                    'status': request.status,
                    'method': request.method,
                    'package_name': request.package_name,
                }
            )
            record_id = result.scalar_one()
            db.commit()

            return SkillInstallationAuditResponse(
                success=True,
                record_id=str(record_id),
                message=f"Started installation audit for {skill_name}"
            )

        # For other statuses: Update most recent STARTED record
        else:
            from sqlalchemy import text

            # Build parameterized update
            params = {
                'skill_name': skill_name,
                'status': request.status,
            }

            set_parts = ["status = :status", "completed_at = NOW()"]

            if request.binary_path:
                set_parts.append("binary_path = :binary_path")
                params['binary_path'] = request.binary_path
            if request.error_message:
                set_parts.append("error_message = :error_message")
                params['error_message'] = request.error_message

            set_clause = ', '.join(set_parts)

            result = db.execute(
                text(f"""
                UPDATE skill_installation_history
                SET {set_clause}
                WHERE id = (
                    SELECT id FROM skill_installation_history
                    WHERE skill_name = :skill_name
                      AND status = 'STARTED'
                    ORDER BY started_at DESC
                    LIMIT 1
                )
                RETURNING id
                """),
                params
            )

            updated_row = result.fetchone()
            if not updated_row:
                raise HTTPException(
                    status_code=404,
                    detail=f"No STARTED installation record found for {skill_name}"
                )

            record_id = updated_row[0]
            db.commit()

            return SkillInstallationAuditResponse(
                success=True,
                record_id=str(record_id),
                message=f"Updated installation audit for {skill_name} to {request.status}"
            )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to record audit event: {str(e)}"
        )


@router.get(
    "/skills/{skill_name}/installation-status",
    summary="Get current installation status",
    description="Get the current installation status for a skill (for UI display)"
)
def get_skill_installation_status(
    skill_name: str,
    db: Session = Depends(get_db)
):
    """
    Get current installation status for a skill.

    Returns the most recent installation record to determine if skill is installed.
    """
    try:
        from sqlalchemy import text
        result = db.execute(
            text("""
            SELECT status, binary_path, completed_at
            FROM skill_installation_history
            WHERE skill_name = :skill_name
            ORDER BY started_at DESC
            LIMIT 1
            """),
            {'skill_name': skill_name}
        )

        row = result.fetchone()

        if not row:
            return {
                'skill_name': skill_name,
                'isInstalled': False,
                'binaryPath': None,
                'status': None
            }

        status = row[0]
        binary_path = row[1]
        completed_at = row[2]

        return {
            'skill_name': skill_name,
            'isInstalled': status == 'COMPLETED',
            'binaryPath': binary_path,
            'status': status,
            'lastUpdated': completed_at.isoformat() if completed_at else None
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve status: {str(e)}"
        )


@router.get(
    "/skills/{skill_name}/installation/history",
    summary="Get skill installation history",
    description="Retrieve installation history for a specific skill"
)
def get_skill_installation_history(
    skill_name: str,
    limit: int = 10,
    db: Session = Depends(get_db)
):
    """
    Get installation history for a skill.

    Returns the most recent installation attempts for the specified skill,
    ordered by most recent first.
    """
    try:
        from sqlalchemy import text
        result = db.execute(
            text("""
            SELECT
                id, skill_name, agent_id, status, method,
                package_name, binary_path, error_message,
                started_at, completed_at, created_at
            FROM skill_installation_history
            WHERE skill_name = :skill_name
            ORDER BY started_at DESC
            LIMIT :limit
            """),
            {'skill_name': skill_name, 'limit': limit}
        )

        rows = result.fetchall()

        history = [
            {
                'id': str(row[0]),
                'skill_name': row[1],
                'agent_id': row[2],
                'status': row[3],
                'method': row[4],
                'package_name': row[5],
                'binary_path': row[6],
                'error_message': row[7],
                'started_at': row[8].isoformat() if row[8] else None,
                'completed_at': row[9].isoformat() if row[9] else None,
                'created_at': row[10].isoformat() if row[10] else None,
            }
            for row in rows
        ]

        return {
            'skill_name': skill_name,
            'count': len(history),
            'history': history
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve history: {str(e)}"
        )
