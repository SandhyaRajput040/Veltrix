"""
Veltrix - Baapstore -> Amazon daily stock sync automation.

Entry point.

Module 1 only proves that project scaffolding and configuration loading
work end to end. Later modules will wire in the real pipeline:
    Drive download -> validation -> Amazon TXT -> SP-API feed -> notification
"""

from src.config.settings import settings


def main() -> None:
    print(f"{settings.app_name} starting up...")
    print(f"Environment: {settings.environment}")
    print(f"Debug mode: {settings.debug}")
    print("Module 1 scaffolding OK. No pipeline modules are wired in yet.")


if __name__ == "__main__":
    main()