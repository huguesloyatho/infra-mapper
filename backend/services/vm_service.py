"""Service CRUD pour la gestion des VMs."""

import logging
import uuid
from typing import Optional, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Vm, Host, VmStatusEnum, OsTypeEnum
from models.schemas import VmCreate, VmUpdate

logger = logging.getLogger(__name__)


class VmService:
    """Service CRUD pour les VMs managées."""

    def __init__(self, db: AsyncSession):
        """Initialise le service."""
        self.db = db

    async def list_vms(self, include_auto_discovered: bool = True) -> List[Vm]:
        """
        Liste toutes les VMs.

        Args:
            include_auto_discovered: Inclure les VMs auto-découvertes

        Returns:
            Liste des VMs
        """
        query = select(Vm)
        if not include_auto_discovered:
            query = query.where(Vm.is_auto_discovered == False)
        query = query.order_by(Vm.name)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_vm(self, vm_id: str) -> Optional[Vm]:
        """
        Récupère une VM par son ID.

        Args:
            vm_id: ID de la VM

        Returns:
            VM ou None
        """
        return await self.db.get(Vm, vm_id)

    async def get_vm_by_host_id(self, host_id: str) -> Optional[Vm]:
        """
        Récupère une VM par son host_id (agent connecté).

        Args:
            host_id: ID de l'hôte

        Returns:
            VM ou None
        """
        result = await self.db.execute(
            select(Vm).where(Vm.host_id == host_id)
        )
        return result.scalar_one_or_none()

    async def get_vm_by_ip(self, ip_address: str) -> Optional[Vm]:
        """
        Récupère une VM par son adresse IP.

        Args:
            ip_address: Adresse IP

        Returns:
            VM ou None
        """
        result = await self.db.execute(
            select(Vm).where(Vm.ip_address == ip_address)
        )
        return result.scalar_one_or_none()

    async def create_vm(self, data: VmCreate) -> Vm:
        """
        Crée une nouvelle VM.

        Args:
            data: Données de création

        Returns:
            VM créée
        """
        vm = Vm(
            id=str(uuid.uuid4()),
            name=data.name,
            hostname=data.hostname,
            ip_address=data.ip_address,
            ssh_port=data.ssh_port,
            ssh_user=data.ssh_user,
            os_type=OsTypeEnum(data.os_type.value) if data.os_type else OsTypeEnum.UNKNOWN,
            status=VmStatusEnum.PENDING,
            tags=data.tags or [],
            notes=data.notes,
            is_auto_discovered=False,
        )
        self.db.add(vm)
        await self.db.commit()
        await self.db.refresh(vm)

        logger.info(f"VM créée: {vm.name} ({vm.ip_address})")
        return vm

    async def update_vm(self, vm_id: str, data: VmUpdate) -> Optional[Vm]:
        """
        Met à jour une VM.

        Args:
            vm_id: ID de la VM
            data: Données de mise à jour

        Returns:
            VM mise à jour ou None
        """
        vm = await self.get_vm(vm_id)
        if not vm:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if key == "os_type" and value is not None:
                value = OsTypeEnum(value.value)
            setattr(vm, key, value)

        await self.db.commit()
        await self.db.refresh(vm)

        logger.info(f"VM mise à jour: {vm.name}")
        return vm

    async def delete_vm(self, vm_id: str) -> bool:
        """
        Supprime une VM.

        Args:
            vm_id: ID de la VM

        Returns:
            True si supprimée
        """
        vm = await self.get_vm(vm_id)
        if not vm:
            return False

        await self.db.delete(vm)
        await self.db.commit()

        logger.info(f"VM supprimée: {vm.name}")
        return True

    async def update_status(self, vm_id: str, status: VmStatusEnum) -> Optional[Vm]:
        """
        Met à jour le statut d'une VM.

        Args:
            vm_id: ID de la VM
            status: Nouveau statut

        Returns:
            VM mise à jour ou None
        """
        vm = await self.get_vm(vm_id)
        if not vm:
            return None

        vm.status = status
        await self.db.commit()
        await self.db.refresh(vm)

        return vm

    async def link_host(self, vm_id: str, host_id: str) -> Optional[Vm]:
        """
        Lie une VM à un hôte (quand l'agent se connecte).

        Args:
            vm_id: ID de la VM
            host_id: ID de l'hôte

        Returns:
            VM mise à jour ou None
        """
        vm = await self.get_vm(vm_id)
        if not vm:
            return None

        vm.host_id = host_id
        vm.status = VmStatusEnum.ONLINE
        await self.db.commit()
        await self.db.refresh(vm)

        logger.info(f"VM {vm.name} liée à l'hôte {host_id}")
        return vm

    async def auto_discover_from_host(self, host: Host) -> Vm:
        """
        Crée ou met à jour une VM depuis un hôte auto-découvert.

        Args:
            host: Hôte découvert

        Returns:
            VM créée ou mise à jour
        """
        # Chercher si une VM existe déjà pour cet hôte
        existing = await self.get_vm_by_host_id(host.id)
        if existing:
            existing.status = VmStatusEnum.ONLINE
            await self.db.commit()
            await self.db.refresh(existing)
            return existing

        # Chercher par IP (Tailscale ou première IP)
        ip_address = host.tailscale_ip
        if not ip_address and host.ip_addresses:
            ip_address = host.ip_addresses[0]
        if not ip_address:
            ip_address = "unknown"

        existing_by_ip = await self.get_vm_by_ip(ip_address)
        if existing_by_ip:
            existing_by_ip.host_id = host.id
            existing_by_ip.status = VmStatusEnum.ONLINE
            await self.db.commit()
            await self.db.refresh(existing_by_ip)
            return existing_by_ip

        # Créer nouvelle VM auto-découverte
        vm = Vm(
            id=str(uuid.uuid4()),
            name=host.hostname,
            hostname=host.hostname,
            ip_address=ip_address,
            host_id=host.id,
            status=VmStatusEnum.ONLINE,
            is_auto_discovered=True,
            tags=[],
        )
        self.db.add(vm)
        await self.db.commit()
        await self.db.refresh(vm)

        logger.info(f"VM auto-découverte: {vm.name} ({vm.ip_address})")
        return vm

    async def mark_offline_if_host_offline(self, host_id: str) -> None:
        """
        Marque une VM comme offline si son hôte est offline.

        Args:
            host_id: ID de l'hôte
        """
        vm = await self.get_vm_by_host_id(host_id)
        if vm and vm.status == VmStatusEnum.ONLINE:
            vm.status = VmStatusEnum.OFFLINE
            await self.db.commit()
            logger.info(f"VM {vm.name} marquée offline")
