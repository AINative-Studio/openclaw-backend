"""
Skill Installation API Endpoints

Provides endpoints for installing, checking, and uninstalling CLI-based OpenClaw skills.
Supports Go and NPM package managers.
"""

from fastapi import APIRouter, HTTPException, status, Path
from typing import Dict, Any
import logging

from backend.schemas.skill_installation import (
    SkillInstallRequest,
    SkillInstallResponse,
    SkillInstallInfoResponse,
    SkillListResponse,
)
from backend.services.skill_installation_service import (
    SkillInstallationService,
    INSTALLABLE_SKILLS,
    InstallMethod,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# Singleton service instance
service = SkillInstallationService()


@router.get(
    "/skills/installable",
    response_model=SkillListResponse,
    status_code=status.HTTP_200_OK,
    summary="List all installable skills",
    description="Returns all skills with installation information (auto-installable and manual)",
)
async def list_installable_skills() -> SkillListResponse:
    """
    Get list of all installable skills with metadata.

    Returns:
        SkillListResponse with all skills, counts by method
    """
    skills = []
    auto_installable = 0
    manual = 0

    for skill_name, skill_data in INSTALLABLE_SKILLS.items():
        method = skill_data["method"]
        is_installable = method in [InstallMethod.GO, InstallMethod.NPM]

        skills.append(
            SkillInstallInfoResponse(
                skill_name=skill_name,
                method=method,
                package=skill_data.get("package"),
                description=skill_data["description"],
                installable=is_installable,
                docs=skill_data.get("docs"),
                requirements=skill_data.get("requirements"),
            )
        )

        if is_installable:
            auto_installable += 1
        else:
            manual += 1

    return SkillListResponse(
        skills=skills,
        total=len(skills),
        auto_installable=auto_installable,
        manual=manual,
    )


@router.get(
    "/skills/{skill_name}/install-info",
    response_model=SkillInstallInfoResponse,
    status_code=status.HTTP_200_OK,
    summary="Get installation info for a skill",
    description="Returns installation method, package name, and requirements for a specific skill",
)
async def get_skill_install_info(
    skill_name: str = Path(..., description="Name of the skill")
) -> SkillInstallInfoResponse:
    """
    Get installation information for a specific skill.

    Args:
        skill_name: Name of the skill

    Returns:
        SkillInstallInfoResponse with installation details

    Raises:
        HTTPException: 404 if skill not found
    """
    skill_name = skill_name.lower().strip()

    if skill_name not in INSTALLABLE_SKILLS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skill '{skill_name}' not found in registry",
        )

    skill_data = INSTALLABLE_SKILLS[skill_name]
    method = skill_data["method"]
    is_installable = method in [InstallMethod.GO, InstallMethod.NPM]

    return SkillInstallInfoResponse(
        skill_name=skill_name,
        method=method,
        package=skill_data.get("package"),
        description=skill_data["description"],
        installable=is_installable,
        docs=skill_data.get("docs"),
        requirements=skill_data.get("requirements"),
    )


@router.post(
    "/skills/{skill_name}/install",
    response_model=SkillInstallResponse,
    status_code=status.HTTP_200_OK,
    summary="Install a skill",
    description="Installs a CLI skill using go install or npm install -g",
)
async def install_skill(
    skill_name: str = Path(..., description="Name of the skill to install"),
    request: SkillInstallRequest = SkillInstallRequest(),
) -> SkillInstallResponse:
    """
    Install a CLI skill using the appropriate package manager.

    Args:
        skill_name: Name of the skill to install
        request: Installation options (force, timeout)

    Returns:
        SkillInstallResponse with installation result and logs

    Raises:
        HTTPException: 400 if skill is not installable, 404 if skill not found
    """
    skill_name = skill_name.lower().strip()

    # Validate skill exists
    if skill_name not in INSTALLABLE_SKILLS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skill '{skill_name}' not found in registry",
        )

    skill_data = INSTALLABLE_SKILLS[skill_name]
    method = skill_data["method"]

    # Check if skill requires manual installation
    if method == InstallMethod.MANUAL:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Skill '{skill_name}' requires manual installation. See docs: {skill_data.get('docs', 'N/A')}",
        )

    logger.info(f"Installing skill '{skill_name}' via {method}")

    # Perform installation
    try:
        # All skills are NEURO skills - use 2-step installation
        if method == InstallMethod.NPM:
            result = await service.install_neuro_skill(
                skill_name=skill_name,
                neuro_package=skill_data["package"],
                timeout=request.timeout,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported installation method: {method}",
            )

        logger.info(f"Installation of '{skill_name}' completed: success={result.success}")

        return SkillInstallResponse(
            success=result.success,
            message=result.message,
            logs=result.logs,
            method=result.method.value if result.method else None,
            package=result.package,
        )

    except Exception as e:
        logger.exception(f"Unexpected error installing '{skill_name}'")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Installation error: {str(e)}",
        )


@router.get(
    "/skills/{skill_name}/installation-status",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Check skill installation status",
    description="Checks if a skill's binary is installed and accessible in PATH",
)
async def check_skill_installation_status(
    skill_name: str = Path(..., description="Name of the skill")
) -> Dict[str, Any]:
    """
    Check if a skill is installed (binary exists in PATH).

    Args:
        skill_name: Name of the skill

    Returns:
        Dict with installation status

    Raises:
        HTTPException: 404 if skill not found
    """
    skill_name = skill_name.lower().strip()

    if skill_name not in INSTALLABLE_SKILLS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skill '{skill_name}' not found in registry",
        )

    skill_data = INSTALLABLE_SKILLS[skill_name]

    # For manual skills, we can't check installation
    if skill_data["method"] == InstallMethod.MANUAL:
        return {
            "skill_name": skill_name,
            "is_installed": False,
            "method": skill_data["method"],
            "message": "Manual installation required - cannot verify",
            "docs": skill_data.get("docs"),
        }

    # Check if binary is in PATH
    import shutil
    binary_path = shutil.which(skill_data.get("binary", skill_name))

    return {
        "skill_name": skill_name,
        "is_installed": binary_path is not None,
        "binary_path": binary_path,
        "method": skill_data["method"],
        "package": skill_data.get("package"),
    }


@router.delete(
    "/skills/{skill_name}/install",
    response_model=SkillInstallResponse,
    status_code=status.HTTP_200_OK,
    summary="Uninstall a skill",
    description="Uninstalls an NPM skill (Go packages must be removed manually)",
)
async def uninstall_skill(
    skill_name: str = Path(..., description="Name of the skill to uninstall"),
) -> SkillInstallResponse:
    """
    Uninstall a CLI skill.

    Note: Go packages cannot be easily uninstalled - user must manually remove binary.

    Args:
        skill_name: Name of the skill to uninstall

    Returns:
        SkillInstallResponse with uninstall result

    Raises:
        HTTPException: 404 if skill not found, 400 if uninstall not supported
    """
    skill_name = skill_name.lower().strip()

    if skill_name not in INSTALLABLE_SKILLS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skill '{skill_name}' not found in registry",
        )

    skill_data = INSTALLABLE_SKILLS[skill_name]
    method = skill_data["method"]

    if method == InstallMethod.GO:
        # Go doesn't have easy uninstall
        import shutil
        binary_path = shutil.which(skill_data.get("binary", skill_name))

        if binary_path:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Go packages must be uninstalled manually. Binary location: {binary_path}",
            )
        else:
            return SkillInstallResponse(
                success=True,
                message=f"Skill '{skill_name}' is not installed",
                logs=["No binary found in PATH"],
            )

    elif method == InstallMethod.NPM:
        logger.info(f"Uninstalling NPM skill '{skill_name}'")

        try:
            import asyncio

            cmd = ["npm", "uninstall", "-g", skill_data["package"]]
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60)

            logs = []
            if stdout:
                logs.extend(stdout.decode("utf-8", errors="replace").strip().split("\n"))
            if stderr:
                logs.extend(stderr.decode("utf-8", errors="replace").strip().split("\n"))

            if process.returncode == 0:
                return SkillInstallResponse(
                    success=True,
                    message=f"Successfully uninstalled '{skill_name}'",
                    logs=logs,
                    method=method,
                    package=skill_data["package"],
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Uninstall failed with exit code {process.returncode}",
                )

        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Uninstall operation timed out",
            )
        except Exception as e:
            logger.exception(f"Error uninstalling '{skill_name}'")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Uninstall error: {str(e)}",
            )

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Skill '{skill_name}' requires manual uninstallation",
        )
