"""Testa o instalador compartilhado em HOMEs isolados, sem tocar no sistema."""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IGNORE = shutil.ignore_patterns(
    ".venv", ".venv.bak-*", ".venv.new.*", "__pycache__", ".git",
)


def write(path, text, mode=0o644):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.chmod(path, mode)


def env_for(home, os_release, path=None):
    env = os.environ.copy()
    env.update({
        "HOME": home,
        "XDG_CONFIG_HOME": os.path.join(home, ".config"),
        "XDG_DATA_HOME": os.path.join(home, ".local", "share"),
        "TMPDIR": os.path.join(home, ".tmp"),
        "FOURCORD_OS_RELEASE_FILE": os_release,
    })
    if path is not None:
        env["PATH"] = path
    os.makedirs(env["TMPDIR"], exist_ok=True)
    return env


def run(project, args, env, timeout=240):
    return subprocess.run(
        ["./install.sh", *args], cwd=project, env=env,
        text=True, capture_output=True, timeout=timeout,
    )


def copy_project(base, name="4Cord Project"):
    project = os.path.join(base, name)
    shutil.copytree(ROOT, project, ignore=IGNORE)
    return project


def main():
    with tempfile.TemporaryDirectory(prefix="4cord-install-audit-") as base:
        project = copy_project(base)
        home = os.path.join(base, "home")
        os.makedirs(home)
        os_release = os.path.join(base, "os-release")
        write(os_release, (
            'ID=ubuntu\nVERSION_ID="26.04"\n'
            'PRETTY_NAME="Ubuntu 26.04 LTS"\n'
        ))

        conf = os.path.join(home, ".config", "4cord")
        settings_path = os.path.join(conf, "settings.json")
        token_path = os.path.join(conf, "token")
        legacy_dir = os.path.join(home, ".config", "trashpanda")
        settings_text = '{"name": "4Cord", "theme": "dark"}\n'
        token_text = "token-de-teste-nao-real\n"
        write(settings_path, settings_text, 0o600)
        write(token_path, token_text, 0o600)
        write(os.path.join(legacy_dir, "settings.json"), '{"legacy": true}\n', 0o600)

        env = env_for(home, os_release)
        first = run(project, [], env)
        assert first.returncode == 0, (first.stdout, first.stderr)
        assert "4Cord 2.4.0 instalado." in first.stdout, first.stdout
        assert "Configuração existente preservada" in first.stdout, first.stdout
        assert "Configuração legada preservada" in first.stdout, first.stdout
        assert "Traceback" not in first.stdout + first.stderr, first.stderr
        assert "ensurepip" not in first.stderr.lower(), first.stderr

        venv_python = os.path.join(project, ".venv", "bin", "python")
        assert os.path.isfile(venv_python), "ambiente virtual não foi criado"
        imports = subprocess.run(
            [venv_python, "-c", "import gi; print('ok')"],
            env=env, text=True, capture_output=True, timeout=60,
        )
        assert imports.returncode == 0 and "ok" in imports.stdout, imports.stderr

        desktop_path = os.path.join(
            home, ".local", "share", "applications", "4cord.desktop")
        with open(desktop_path, encoding="utf-8") as fh:
            desktop = fh.read()
        launcher = os.path.join(project, "bin", "4cord")
        assert f'Exec="{launcher}"' in desktop, desktop
        assert "StartupWMClass=4cord" in desktop, desktop
        assert "Name=4Cord" in desktop, desktop

        user_link = os.path.join(home, ".local", "bin", "4cord")
        assert os.path.islink(user_link), "link do comando não foi criado"
        assert os.path.realpath(user_link) == os.path.realpath(launcher)

        with open(settings_path, encoding="utf-8") as fh:
            assert fh.read() == settings_text
        with open(token_path, encoding="utf-8") as fh:
            assert fh.read() == token_text
        assert stat.S_IMODE(os.stat(token_path).st_mode) == 0o600
        assert os.path.isfile(os.path.join(legacy_dir, "settings.json"))

        second = run(project, [], env)
        assert second.returncode == 0, (second.stdout, second.stderr)
        assert "Criando ambiente virtual" not in second.stdout, second.stdout
        assert "4Cord 2.4.0 instalado." in second.stdout
        with open(settings_path, encoding="utf-8") as fh:
            assert fh.read() == settings_text
        assert not [
            name for name in os.listdir(project) if name.startswith(".venv.new.")
        ]

        # --check não deve criar ambiente, link ou atalho.
        check_project = copy_project(base, "4Cord Check")
        check_home = os.path.join(base, "check-home")
        os.makedirs(check_home)
        check_env = env_for(check_home, os_release)
        checked = run(check_project, ["--check"], check_env)
        assert checked.returncode == 0, (checked.stdout, checked.stderr)
        assert "Dependências nativas: OK" in checked.stdout, checked.stdout
        assert not os.path.exists(os.path.join(check_project, ".venv"))
        assert not os.path.exists(os.path.join(
            check_home, ".local", "bin", "4cord"))
        assert not os.path.exists(os.path.join(
            check_home, ".local", "share", "applications", "4cord.desktop"))

        # Dependências ausentes: explica os comandos e não instala nada.
        fake_bin = os.path.join(base, "fake-bin")
        os.makedirs(fake_bin)
        write(os.path.join(fake_bin, "dpkg-query"),
              "#!/bin/sh\nexit 1\n", 0o755)
        write(os.path.join(fake_bin, "pacman"),
              "#!/bin/sh\nexit 1\n", 0o755)
        missing_home = os.path.join(base, "missing-home")
        os.makedirs(missing_home)
        missing_env = env_for(
            missing_home, os_release, fake_bin + os.pathsep + os.environ["PATH"])
        missing = run(check_project, ["--check"], missing_env)
        assert missing.returncode != 0
        missing_out = missing.stdout + missing.stderr
        assert "Dependências do sistema ausentes" in missing_out, missing_out
        assert "sudo apt-get update" in missing_out, missing_out
        assert "sudo apt-get install --no-install-recommends" in missing_out
        assert "python3-gi" in missing_out, missing_out
        assert "gir1.2-webkit2-4.1" in missing_out, missing_out
        assert "pacman" not in missing_out.lower(), missing_out
        assert not os.path.exists(os.path.join(check_project, ".venv"))

        # Caminho Arch: confere os nomes de pacotes e o comando pacman.
        arch_release = os.path.join(base, "arch-release")
        write(arch_release, (
            'ID=arch\nPRETTY_NAME="Arch Linux"\n'
        ))
        arch_home = os.path.join(base, "arch-home")
        os.makedirs(arch_home)
        arch_env = env_for(
            arch_home, arch_release, fake_bin + os.pathsep + os.environ["PATH"])
        arch = run(check_project, ["--check"], arch_env)
        arch_out = arch.stdout + arch.stderr
        assert arch.returncode != 0, arch_out
        assert "sudo pacman -S --needed" in arch_out, arch_out
        for package in ("python-gobject", "gtk3", "webkit2gtk-4.1",
                        "gdk-pixbuf2"):
            assert package in arch_out, (package, arch_out)
        assert "apt-get" not in arch_out, arch_out

        # Ambiente virtual inválido: recusa sem a opção e cria backup com ela.
        broken_project = copy_project(base, "4Cord Broken")
        broken_home = os.path.join(base, "broken-home")
        os.makedirs(broken_home)
        broken_conf = os.path.join(broken_home, ".config", "4cord")
        write(os.path.join(broken_conf, "settings.json"),
              '{"name": "4Cord", "theme": "amoled"}\n', 0o600)
        os.makedirs(os.path.join(broken_project, ".venv"))
        write(os.path.join(broken_project, ".venv", "invalido.txt"), "x\n")
        broken_env = env_for(broken_home, os_release)
        refused = run(broken_project, [], broken_env)
        refused_out = refused.stdout + refused.stderr
        assert refused.returncode != 0, refused_out
        assert "--recreate-venv" in refused_out, refused_out
        assert os.path.isfile(os.path.join(
            broken_project, ".venv", "invalido.txt"))
        recreated = run(broken_project, ["--recreate-venv"], broken_env)
        recreated_out = recreated.stdout + recreated.stderr
        assert recreated.returncode == 0, recreated_out
        backups = [
            name for name in os.listdir(broken_project)
            if name.startswith(".venv.bak-")
        ]
        assert len(backups) == 1, backups
        assert os.path.isfile(os.path.join(
            broken_project, backups[0], "invalido.txt"))
        assert os.path.isfile(os.path.join(
            broken_project, ".venv", "bin", "python"))
        with open(os.path.join(broken_conf, "settings.json"),
                  encoding="utf-8") as fh:
            assert fh.read() == '{"name": "4Cord", "theme": "amoled"}\n'

        unsupported_release = os.path.join(base, "debian-release")
        write(unsupported_release, 'ID=debian\nPRETTY_NAME="Debian GNU/Linux"\n')
        unsupported_home = os.path.join(base, "unsupported-home")
        os.makedirs(unsupported_home)
        unsupported_env = env_for(unsupported_home, unsupported_release)
        unsupported = run(check_project, ["--check"], unsupported_env)
        assert unsupported.returncode == 2, (
            unsupported.returncode, unsupported.stdout, unsupported.stderr)
        unsupported_out = unsupported.stdout + unsupported.stderr
        assert "distribuição não reconhecida" in unsupported_out, unsupported_out
        assert "Ubuntu 26.04 e Arch Linux" in unsupported_out, unsupported_out

        help_run = run(project, ["--help"], env)
        assert help_run.returncode == 0
        assert "--recreate-venv" in help_run.stdout

        print("INSTALL_AUDIT " + json.dumps({
            "first_install": first.returncode,
            "second_install": second.returncode,
            "check": checked.returncode,
            "missing_deps": missing.returncode,
            "arch_path": arch.returncode,
            "unsupported": unsupported.returncode,
            "recreate_venv": True,
            "venv": True,
            "desktop": True,
            "config_preserved": True,
        }, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except AssertionError as exc:
        print("INSTALL_AUDIT_FALHA " + str(exc), file=sys.stderr)
        raise
