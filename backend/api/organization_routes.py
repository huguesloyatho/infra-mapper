"""Organization and Team management routes for multi-tenancy."""

import uuid
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.database import get_db
from db.auth_models import (
    Organization, OrganizationMember, Team, TeamMember,
    OrganizationHost, TeamHost, OrganizationRole, TeamRole, User
)
from db.models import Host
from api.dependencies import get_current_user, require_role
from db.auth_models import RoleEnum

router = APIRouter(prefix="/api/v1/organizations", tags=["organizations"])


# =============================================================================
# Pydantic Schemas
# =============================================================================

class OrganizationCreate(BaseModel):
    """Schéma pour créer une organisation."""
    name: str = Field(..., min_length=1, max_length=100)
    slug: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")
    description: Optional[str] = None
    max_hosts: Optional[int] = None
    max_users: Optional[int] = None
    max_teams: Optional[int] = None


class OrganizationUpdate(BaseModel):
    """Schéma pour mettre à jour une organisation."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    is_active: Optional[bool] = None
    max_hosts: Optional[int] = None
    max_users: Optional[int] = None
    max_teams: Optional[int] = None
    settings: Optional[dict] = None


class OrganizationResponse(BaseModel):
    """Réponse pour une organisation."""
    id: str
    name: str
    slug: str
    description: Optional[str]
    is_active: bool
    max_hosts: Optional[int]
    max_users: Optional[int]
    max_teams: Optional[int]
    settings: dict
    members_count: int = 0
    teams_count: int = 0
    hosts_count: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


class TeamCreate(BaseModel):
    """Schéma pour créer une équipe."""
    name: str = Field(..., min_length=1, max_length=100)
    slug: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")
    description: Optional[str] = None
    color: Optional[str] = Field(None, pattern=r"^#[0-9a-fA-F]{6}$")


class TeamUpdate(BaseModel):
    """Schéma pour mettre à jour une équipe."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    color: Optional[str] = Field(None, pattern=r"^#[0-9a-fA-F]{6}$")
    is_active: Optional[bool] = None


class TeamResponse(BaseModel):
    """Réponse pour une équipe."""
    id: str
    organization_id: str
    name: str
    slug: str
    description: Optional[str]
    color: Optional[str]
    is_active: bool
    members_count: int = 0
    hosts_count: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


class MemberAdd(BaseModel):
    """Schéma pour ajouter un membre."""
    user_id: str
    role: OrganizationRole = OrganizationRole.MEMBER


class TeamMemberAdd(BaseModel):
    """Schéma pour ajouter un membre à une équipe."""
    user_id: str
    role: TeamRole = TeamRole.MEMBER


class HostAssign(BaseModel):
    """Schéma pour assigner un host."""
    host_id: str


class TeamHostAssign(BaseModel):
    """Schéma pour assigner un host à une équipe."""
    host_id: str
    can_view: bool = True
    can_manage: bool = False


# =============================================================================
# Organization Routes
# =============================================================================

@router.get("", response_model=List[OrganizationResponse])
async def list_organizations(
    db: AsyncSession = Depends(get_db),
    include_inactive: bool = Query(False),
    current_user: User = Depends(get_current_user),
):
    """Liste les organisations accessibles à l'utilisateur."""
    # Super admin voit tout
    if current_user.role == RoleEnum.SUPER_ADMIN:
        query = select(Organization)
        if not include_inactive:
            query = query.where(Organization.is_active == True)
    else:
        # Les autres voient seulement leurs organisations
        query = (
            select(Organization)
            .join(OrganizationMember, OrganizationMember.organization_id == Organization.id)
            .where(OrganizationMember.user_id == current_user.id)
        )
        if not include_inactive:
            query = query.where(Organization.is_active == True)

    query = query.order_by(Organization.name)
    result = await db.execute(query)
    organizations = result.scalars().all()

    # Récupérer les comptages
    responses = []
    for org in organizations:
        # Count members
        members_result = await db.execute(
            select(func.count(OrganizationMember.id))
            .where(OrganizationMember.organization_id == org.id)
        )
        members_count = members_result.scalar() or 0

        # Count teams
        teams_result = await db.execute(
            select(func.count(Team.id))
            .where(Team.organization_id == org.id)
        )
        teams_count = teams_result.scalar() or 0

        # Count hosts
        hosts_result = await db.execute(
            select(func.count(OrganizationHost.id))
            .where(OrganizationHost.organization_id == org.id)
        )
        hosts_count = hosts_result.scalar() or 0

        responses.append(OrganizationResponse(
            id=org.id,
            name=org.name,
            slug=org.slug,
            description=org.description,
            is_active=org.is_active,
            max_hosts=org.max_hosts,
            max_users=org.max_users,
            max_teams=org.max_teams,
            settings=org.settings or {},
            members_count=members_count,
            teams_count=teams_count,
            hosts_count=hosts_count,
            created_at=org.created_at,
        ))

    return responses


@router.post("", response_model=OrganizationResponse)
async def create_organization(
    data: OrganizationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([RoleEnum.SUPER_ADMIN])),
):
    """Crée une nouvelle organisation (super admin uniquement)."""
    # Vérifier que le slug est unique
    existing = await db.execute(
        select(Organization).where(Organization.slug == data.slug)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Slug already exists")

    org = Organization(
        id=str(uuid.uuid4()),
        name=data.name,
        slug=data.slug,
        description=data.description,
        max_hosts=data.max_hosts,
        max_users=data.max_users,
        max_teams=data.max_teams,
    )

    db.add(org)
    await db.commit()
    await db.refresh(org)

    return OrganizationResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        description=org.description,
        is_active=org.is_active,
        max_hosts=org.max_hosts,
        max_users=org.max_users,
        max_teams=org.max_teams,
        settings=org.settings or {},
        members_count=0,
        teams_count=0,
        hosts_count=0,
        created_at=org.created_at,
    )


@router.get("/{org_id}", response_model=OrganizationResponse)
async def get_organization(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Récupère une organisation par ID."""
    org = await _get_org_with_access(db, org_id, current_user)

    # Comptages
    members_count = (await db.execute(
        select(func.count(OrganizationMember.id))
        .where(OrganizationMember.organization_id == org.id)
    )).scalar() or 0

    teams_count = (await db.execute(
        select(func.count(Team.id))
        .where(Team.organization_id == org.id)
    )).scalar() or 0

    hosts_count = (await db.execute(
        select(func.count(OrganizationHost.id))
        .where(OrganizationHost.organization_id == org.id)
    )).scalar() or 0

    return OrganizationResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        description=org.description,
        is_active=org.is_active,
        max_hosts=org.max_hosts,
        max_users=org.max_users,
        max_teams=org.max_teams,
        settings=org.settings or {},
        members_count=members_count,
        teams_count=teams_count,
        hosts_count=hosts_count,
        created_at=org.created_at,
    )


@router.put("/{org_id}", response_model=OrganizationResponse)
async def update_organization(
    org_id: str,
    data: OrganizationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Met à jour une organisation."""
    org = await _get_org_with_access(db, org_id, current_user, require_admin=True)

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(org, field, value)

    await db.commit()
    await db.refresh(org)

    # Comptages
    members_count = (await db.execute(
        select(func.count(OrganizationMember.id))
        .where(OrganizationMember.organization_id == org.id)
    )).scalar() or 0

    teams_count = (await db.execute(
        select(func.count(Team.id))
        .where(Team.organization_id == org.id)
    )).scalar() or 0

    hosts_count = (await db.execute(
        select(func.count(OrganizationHost.id))
        .where(OrganizationHost.organization_id == org.id)
    )).scalar() or 0

    return OrganizationResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        description=org.description,
        is_active=org.is_active,
        max_hosts=org.max_hosts,
        max_users=org.max_users,
        max_teams=org.max_teams,
        settings=org.settings or {},
        members_count=members_count,
        teams_count=teams_count,
        hosts_count=hosts_count,
        created_at=org.created_at,
    )


@router.delete("/{org_id}")
async def delete_organization(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([RoleEnum.SUPER_ADMIN])),
):
    """Supprime une organisation (super admin uniquement)."""
    result = await db.execute(
        select(Organization).where(Organization.id == org_id)
    )
    org = result.scalar_one_or_none()

    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    await db.delete(org)
    await db.commit()

    return {"status": "deleted", "id": org_id}


# =============================================================================
# Organization Members Routes
# =============================================================================

@router.get("/{org_id}/members")
async def list_organization_members(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Liste les membres d'une organisation."""
    await _get_org_with_access(db, org_id, current_user)

    result = await db.execute(
        select(OrganizationMember, User)
        .join(User, OrganizationMember.user_id == User.id)
        .where(OrganizationMember.organization_id == org_id)
        .order_by(User.username)
    )
    members = result.all()

    return [
        {
            "id": m.OrganizationMember.id,
            "user_id": m.User.id,
            "username": m.User.username,
            "email": m.User.email,
            "display_name": m.User.display_name,
            "role": m.OrganizationMember.role.value,
            "is_default": m.OrganizationMember.is_default,
            "joined_at": m.OrganizationMember.joined_at,
        }
        for m in members
    ]


@router.post("/{org_id}/members")
async def add_organization_member(
    org_id: str,
    data: MemberAdd,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Ajoute un membre à une organisation."""
    org = await _get_org_with_access(db, org_id, current_user, require_admin=True)

    # Vérifier que l'utilisateur existe
    user_result = await db.execute(select(User).where(User.id == data.user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Vérifier qu'il n'est pas déjà membre
    existing = await db.execute(
        select(OrganizationMember).where(
            and_(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.user_id == data.user_id
            )
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="User is already a member")

    # Vérifier les quotas
    if org.max_users:
        count_result = await db.execute(
            select(func.count(OrganizationMember.id))
            .where(OrganizationMember.organization_id == org_id)
        )
        if count_result.scalar() >= org.max_users:
            raise HTTPException(status_code=400, detail="Maximum users limit reached")

    member = OrganizationMember(
        organization_id=org_id,
        user_id=data.user_id,
        role=data.role,
        invited_by=current_user.id,
    )

    db.add(member)
    await db.commit()

    return {"status": "added", "user_id": data.user_id, "role": data.role.value}


@router.put("/{org_id}/members/{user_id}")
async def update_organization_member(
    org_id: str,
    user_id: str,
    role: OrganizationRole,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Met à jour le rôle d'un membre."""
    await _get_org_with_access(db, org_id, current_user, require_admin=True)

    result = await db.execute(
        select(OrganizationMember).where(
            and_(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.user_id == user_id
            )
        )
    )
    member = result.scalar_one_or_none()

    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    member.role = role
    await db.commit()

    return {"status": "updated", "user_id": user_id, "role": role.value}


@router.delete("/{org_id}/members/{user_id}")
async def remove_organization_member(
    org_id: str,
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retire un membre d'une organisation."""
    await _get_org_with_access(db, org_id, current_user, require_admin=True)

    result = await db.execute(
        select(OrganizationMember).where(
            and_(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.user_id == user_id
            )
        )
    )
    member = result.scalar_one_or_none()

    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    await db.delete(member)
    await db.commit()

    return {"status": "removed", "user_id": user_id}


# =============================================================================
# Organization Hosts Routes
# =============================================================================

@router.get("/{org_id}/hosts")
async def list_organization_hosts(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Liste les hosts d'une organisation."""
    await _get_org_with_access(db, org_id, current_user)

    result = await db.execute(
        select(OrganizationHost, Host)
        .join(Host, OrganizationHost.host_id == Host.id)
        .where(OrganizationHost.organization_id == org_id)
        .order_by(Host.hostname)
    )
    hosts = result.all()

    return [
        {
            "assignment_id": h.OrganizationHost.id,
            "host_id": h.Host.id,
            "hostname": h.Host.hostname,
            "ip_addresses": h.Host.ip_addresses,
            "is_online": h.Host.is_online,
            "assigned_at": h.OrganizationHost.assigned_at,
        }
        for h in hosts
    ]


@router.post("/{org_id}/hosts")
async def assign_host_to_organization(
    org_id: str,
    data: HostAssign,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Assigne un host à une organisation."""
    org = await _get_org_with_access(db, org_id, current_user, require_admin=True)

    # Vérifier que le host existe
    host_result = await db.execute(select(Host).where(Host.id == data.host_id))
    host = host_result.scalar_one_or_none()
    if not host:
        raise HTTPException(status_code=404, detail="Host not found")

    # Vérifier qu'il n'est pas déjà assigné (à n'importe quelle org)
    existing = await db.execute(
        select(OrganizationHost).where(OrganizationHost.host_id == data.host_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Host is already assigned to an organization")

    # Vérifier les quotas
    if org.max_hosts:
        count_result = await db.execute(
            select(func.count(OrganizationHost.id))
            .where(OrganizationHost.organization_id == org_id)
        )
        if count_result.scalar() >= org.max_hosts:
            raise HTTPException(status_code=400, detail="Maximum hosts limit reached")

    assignment = OrganizationHost(
        organization_id=org_id,
        host_id=data.host_id,
        assigned_by=current_user.id,
    )

    db.add(assignment)
    await db.commit()

    return {"status": "assigned", "host_id": data.host_id}


@router.delete("/{org_id}/hosts/{host_id}")
async def unassign_host_from_organization(
    org_id: str,
    host_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retire un host d'une organisation."""
    await _get_org_with_access(db, org_id, current_user, require_admin=True)

    result = await db.execute(
        select(OrganizationHost).where(
            and_(
                OrganizationHost.organization_id == org_id,
                OrganizationHost.host_id == host_id
            )
        )
    )
    assignment = result.scalar_one_or_none()

    if not assignment:
        raise HTTPException(status_code=404, detail="Host assignment not found")

    await db.delete(assignment)
    await db.commit()

    return {"status": "unassigned", "host_id": host_id}


# =============================================================================
# Team Routes
# =============================================================================

@router.get("/{org_id}/teams", response_model=List[TeamResponse])
async def list_teams(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Liste les équipes d'une organisation."""
    await _get_org_with_access(db, org_id, current_user)

    result = await db.execute(
        select(Team)
        .where(Team.organization_id == org_id)
        .order_by(Team.name)
    )
    teams = result.scalars().all()

    responses = []
    for team in teams:
        members_count = (await db.execute(
            select(func.count(TeamMember.id))
            .where(TeamMember.team_id == team.id)
        )).scalar() or 0

        hosts_count = (await db.execute(
            select(func.count(TeamHost.id))
            .where(TeamHost.team_id == team.id)
        )).scalar() or 0

        responses.append(TeamResponse(
            id=team.id,
            organization_id=team.organization_id,
            name=team.name,
            slug=team.slug,
            description=team.description,
            color=team.color,
            is_active=team.is_active,
            members_count=members_count,
            hosts_count=hosts_count,
            created_at=team.created_at,
        ))

    return responses


@router.post("/{org_id}/teams", response_model=TeamResponse)
async def create_team(
    org_id: str,
    data: TeamCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Crée une nouvelle équipe."""
    org = await _get_org_with_access(db, org_id, current_user, require_admin=True)

    # Vérifier que le slug est unique dans l'org
    existing = await db.execute(
        select(Team).where(
            and_(Team.organization_id == org_id, Team.slug == data.slug)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Team slug already exists in this organization")

    # Vérifier les quotas
    if org.max_teams:
        count_result = await db.execute(
            select(func.count(Team.id))
            .where(Team.organization_id == org_id)
        )
        if count_result.scalar() >= org.max_teams:
            raise HTTPException(status_code=400, detail="Maximum teams limit reached")

    team = Team(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        name=data.name,
        slug=data.slug,
        description=data.description,
        color=data.color,
    )

    db.add(team)
    await db.commit()
    await db.refresh(team)

    return TeamResponse(
        id=team.id,
        organization_id=team.organization_id,
        name=team.name,
        slug=team.slug,
        description=team.description,
        color=team.color,
        is_active=team.is_active,
        members_count=0,
        hosts_count=0,
        created_at=team.created_at,
    )


@router.get("/{org_id}/teams/{team_id}", response_model=TeamResponse)
async def get_team(
    org_id: str,
    team_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Récupère une équipe."""
    await _get_org_with_access(db, org_id, current_user)

    result = await db.execute(
        select(Team).where(
            and_(Team.id == team_id, Team.organization_id == org_id)
        )
    )
    team = result.scalar_one_or_none()

    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    members_count = (await db.execute(
        select(func.count(TeamMember.id))
        .where(TeamMember.team_id == team.id)
    )).scalar() or 0

    hosts_count = (await db.execute(
        select(func.count(TeamHost.id))
        .where(TeamHost.team_id == team.id)
    )).scalar() or 0

    return TeamResponse(
        id=team.id,
        organization_id=team.organization_id,
        name=team.name,
        slug=team.slug,
        description=team.description,
        color=team.color,
        is_active=team.is_active,
        members_count=members_count,
        hosts_count=hosts_count,
        created_at=team.created_at,
    )


@router.put("/{org_id}/teams/{team_id}", response_model=TeamResponse)
async def update_team(
    org_id: str,
    team_id: str,
    data: TeamUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Met à jour une équipe."""
    await _get_org_with_access(db, org_id, current_user, require_admin=True)

    result = await db.execute(
        select(Team).where(
            and_(Team.id == team_id, Team.organization_id == org_id)
        )
    )
    team = result.scalar_one_or_none()

    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(team, field, value)

    await db.commit()
    await db.refresh(team)

    members_count = (await db.execute(
        select(func.count(TeamMember.id))
        .where(TeamMember.team_id == team.id)
    )).scalar() or 0

    hosts_count = (await db.execute(
        select(func.count(TeamHost.id))
        .where(TeamHost.team_id == team.id)
    )).scalar() or 0

    return TeamResponse(
        id=team.id,
        organization_id=team.organization_id,
        name=team.name,
        slug=team.slug,
        description=team.description,
        color=team.color,
        is_active=team.is_active,
        members_count=members_count,
        hosts_count=hosts_count,
        created_at=team.created_at,
    )


@router.delete("/{org_id}/teams/{team_id}")
async def delete_team(
    org_id: str,
    team_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Supprime une équipe."""
    await _get_org_with_access(db, org_id, current_user, require_admin=True)

    result = await db.execute(
        select(Team).where(
            and_(Team.id == team_id, Team.organization_id == org_id)
        )
    )
    team = result.scalar_one_or_none()

    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    await db.delete(team)
    await db.commit()

    return {"status": "deleted", "id": team_id}


# =============================================================================
# Team Members Routes
# =============================================================================

@router.get("/{org_id}/teams/{team_id}/members")
async def list_team_members(
    org_id: str,
    team_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Liste les membres d'une équipe."""
    await _get_org_with_access(db, org_id, current_user)

    # Vérifier que l'équipe existe
    team_result = await db.execute(
        select(Team).where(and_(Team.id == team_id, Team.organization_id == org_id))
    )
    if not team_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Team not found")

    result = await db.execute(
        select(TeamMember, User)
        .join(User, TeamMember.user_id == User.id)
        .where(TeamMember.team_id == team_id)
        .order_by(User.username)
    )
    members = result.all()

    return [
        {
            "id": m.TeamMember.id,
            "user_id": m.User.id,
            "username": m.User.username,
            "email": m.User.email,
            "display_name": m.User.display_name,
            "role": m.TeamMember.role.value,
            "joined_at": m.TeamMember.joined_at,
        }
        for m in members
    ]


@router.post("/{org_id}/teams/{team_id}/members")
async def add_team_member(
    org_id: str,
    team_id: str,
    data: TeamMemberAdd,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Ajoute un membre à une équipe."""
    await _get_org_with_access(db, org_id, current_user, require_admin=True)

    # Vérifier que l'équipe existe
    team_result = await db.execute(
        select(Team).where(and_(Team.id == team_id, Team.organization_id == org_id))
    )
    if not team_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Team not found")

    # Vérifier que l'utilisateur est membre de l'organisation
    org_member = await db.execute(
        select(OrganizationMember).where(
            and_(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.user_id == data.user_id
            )
        )
    )
    if not org_member.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="User must be a member of the organization first")

    # Vérifier qu'il n'est pas déjà membre de l'équipe
    existing = await db.execute(
        select(TeamMember).where(
            and_(TeamMember.team_id == team_id, TeamMember.user_id == data.user_id)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="User is already a team member")

    member = TeamMember(
        team_id=team_id,
        user_id=data.user_id,
        role=data.role,
        added_by=current_user.id,
    )

    db.add(member)
    await db.commit()

    return {"status": "added", "user_id": data.user_id, "role": data.role.value}


@router.delete("/{org_id}/teams/{team_id}/members/{user_id}")
async def remove_team_member(
    org_id: str,
    team_id: str,
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retire un membre d'une équipe."""
    await _get_org_with_access(db, org_id, current_user, require_admin=True)

    result = await db.execute(
        select(TeamMember).where(
            and_(TeamMember.team_id == team_id, TeamMember.user_id == user_id)
        )
    )
    member = result.scalar_one_or_none()

    if not member:
        raise HTTPException(status_code=404, detail="Team member not found")

    await db.delete(member)
    await db.commit()

    return {"status": "removed", "user_id": user_id}


# =============================================================================
# Team Hosts Routes
# =============================================================================

@router.get("/{org_id}/teams/{team_id}/hosts")
async def list_team_hosts(
    org_id: str,
    team_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Liste les hosts accessibles à une équipe."""
    await _get_org_with_access(db, org_id, current_user)

    # Vérifier que l'équipe existe
    team_result = await db.execute(
        select(Team).where(and_(Team.id == team_id, Team.organization_id == org_id))
    )
    if not team_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Team not found")

    result = await db.execute(
        select(TeamHost, Host)
        .join(Host, TeamHost.host_id == Host.id)
        .where(TeamHost.team_id == team_id)
        .order_by(Host.hostname)
    )
    hosts = result.all()

    return [
        {
            "assignment_id": h.TeamHost.id,
            "host_id": h.Host.id,
            "hostname": h.Host.hostname,
            "ip_addresses": h.Host.ip_addresses,
            "is_online": h.Host.is_online,
            "can_view": h.TeamHost.can_view,
            "can_manage": h.TeamHost.can_manage,
            "assigned_at": h.TeamHost.assigned_at,
        }
        for h in hosts
    ]


@router.post("/{org_id}/teams/{team_id}/hosts")
async def assign_host_to_team(
    org_id: str,
    team_id: str,
    data: TeamHostAssign,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Assigne un host à une équipe."""
    await _get_org_with_access(db, org_id, current_user, require_admin=True)

    # Vérifier que l'équipe existe
    team_result = await db.execute(
        select(Team).where(and_(Team.id == team_id, Team.organization_id == org_id))
    )
    if not team_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Team not found")

    # Vérifier que le host appartient à l'organisation
    org_host = await db.execute(
        select(OrganizationHost).where(
            and_(
                OrganizationHost.organization_id == org_id,
                OrganizationHost.host_id == data.host_id
            )
        )
    )
    if not org_host.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Host must belong to the organization first")

    # Vérifier que le host n'est pas déjà assigné à l'équipe
    existing = await db.execute(
        select(TeamHost).where(
            and_(TeamHost.team_id == team_id, TeamHost.host_id == data.host_id)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Host is already assigned to this team")

    assignment = TeamHost(
        team_id=team_id,
        host_id=data.host_id,
        can_view=data.can_view,
        can_manage=data.can_manage,
    )

    db.add(assignment)
    await db.commit()

    return {"status": "assigned", "host_id": data.host_id}


@router.delete("/{org_id}/teams/{team_id}/hosts/{host_id}")
async def unassign_host_from_team(
    org_id: str,
    team_id: str,
    host_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retire un host d'une équipe."""
    await _get_org_with_access(db, org_id, current_user, require_admin=True)

    result = await db.execute(
        select(TeamHost).where(
            and_(TeamHost.team_id == team_id, TeamHost.host_id == host_id)
        )
    )
    assignment = result.scalar_one_or_none()

    if not assignment:
        raise HTTPException(status_code=404, detail="Host assignment not found")

    await db.delete(assignment)
    await db.commit()

    return {"status": "unassigned", "host_id": host_id}


# =============================================================================
# Helper Functions
# =============================================================================

async def _get_org_with_access(
    db: AsyncSession,
    org_id: str,
    current_user: User,
    require_admin: bool = False,
) -> Organization:
    """Récupère une organisation et vérifie les droits d'accès."""
    result = await db.execute(
        select(Organization).where(Organization.id == org_id)
    )
    org = result.scalar_one_or_none()

    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Super admin a accès à tout
    if current_user.role == RoleEnum.SUPER_ADMIN:
        return org

    # Vérifier que l'utilisateur est membre
    member_result = await db.execute(
        select(OrganizationMember).where(
            and_(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.user_id == current_user.id
            )
        )
    )
    member = member_result.scalar_one_or_none()

    if not member:
        raise HTTPException(status_code=403, detail="Access denied to this organization")

    if require_admin and member.role not in [OrganizationRole.OWNER, OrganizationRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Admin access required")

    return org
