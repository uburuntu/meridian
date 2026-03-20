"""Tests for Ansible infrastructure module."""

from __future__ import annotations

from pathlib import Path

import yaml

from meridian.ansible import get_playbooks_dir, write_inventory


class TestGetPlaybooksDir:
    def test_returns_real_path(self) -> None:
        d = get_playbooks_dir()
        assert d.exists()
        assert d.is_dir()

    def test_contains_playbooks(self) -> None:
        d = get_playbooks_dir()
        assert (d / "playbook.yml").exists()
        assert (d / "playbook-client.yml").exists()
        assert (d / "playbook-uninstall.yml").exists()

    def test_contains_ansible_cfg(self) -> None:
        d = get_playbooks_dir()
        assert (d / "ansible.cfg").exists()

    def test_contains_roles(self) -> None:
        d = get_playbooks_dir()
        assert (d / "roles").is_dir()
        assert (d / "roles" / "xray").is_dir()
        assert (d / "roles" / "common").is_dir()

    def test_contains_group_vars(self) -> None:
        d = get_playbooks_dir()
        assert (d / "group_vars" / "all.yml").exists()


class TestWriteInventory:
    def test_remote_inventory(self, tmp_home: Path) -> None:
        inv = write_inventory("1.2.3.4", "root", local_mode=False)
        assert inv.exists()
        data = yaml.safe_load(inv.read_text())
        host = data["all"]["hosts"]["server"]
        assert host["ansible_host"] == "1.2.3.4"
        assert host["ansible_user"] == "root"
        assert "ansible_connection" not in host

    def test_local_mode_inventory(self, tmp_home: Path) -> None:
        inv = write_inventory("1.2.3.4", "root", local_mode=True)
        data = yaml.safe_load(inv.read_text())
        host = data["all"]["hosts"]["server"]
        assert host["ansible_connection"] == "local"
        assert "ansible_host" not in host

    def test_non_root_gets_become(self, tmp_home: Path) -> None:
        inv = write_inventory("1.2.3.4", "ubuntu", local_mode=False)
        data = yaml.safe_load(inv.read_text())
        host = data["all"]["hosts"]["server"]
        assert host["ansible_become"] is True

    def test_root_no_become(self, tmp_home: Path) -> None:
        inv = write_inventory("1.2.3.4", "root", local_mode=False)
        data = yaml.safe_load(inv.read_text())
        host = data["all"]["hosts"]["server"]
        assert "ansible_become" not in host
