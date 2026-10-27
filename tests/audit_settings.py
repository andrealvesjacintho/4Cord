import hashlib
import json
import os
import stat
import sys
import tempfile
import threading

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
import app
import core.log as clog

base = tempfile.mkdtemp(prefix='4cord-audit-', dir='/tmp/opencode')
app.CONF_DIR = base
app.SETTINGS_FILE = os.path.join(base, 'settings.json')
app.TOKEN_FILE = os.path.join(base, 'token')
# Referencias legadas usadas de proposito para validar a migracao.
app.LEGACY_CONF_DIR = os.path.join(base, 'legacy')
app.MIGRATION_MARKER = os.path.join(base, '.migrated-from-trashpanda')
clog.CONF_DIR = base
clog.LOG_FILE = os.path.join(base, 'log.txt')
os.makedirs(app.LEGACY_CONF_DIR)

legacy_token = os.path.join(app.LEGACY_CONF_DIR, 'token')
legacy_settings = os.path.join(app.LEGACY_CONF_DIR, 'settings.json')
with open(legacy_token, 'w', encoding='utf-8') as fh:
    fh.write('fake-legacy-credential')
with open(legacy_settings, 'w', encoding='utf-8') as fh:
    json.dump({'name': 'TrashPanda', 'theme': 'amoled'}, fh)
os.chmod(legacy_token, 0o644)
os.chmod(legacy_settings, 0o664)

def digest(path):
    with open(path, 'rb') as fh:
        return hashlib.sha256(fh.read()).hexdigest()

legacy_before = (digest(legacy_token), digest(legacy_settings))

# 1. primeira migracao copia e corrige permissoes/nome
app.migrate_legacy_config()
with open(app.TOKEN_FILE, encoding='utf-8') as fh:
    copied_token = fh.read()
with open(app.SETTINGS_FILE, encoding='utf-8') as fh:
    copied_settings = json.load(fh)
migrated = {
    'token_copied': copied_token == 'fake-legacy-credential',
    'name_normalized': copied_settings.get('name') == '4Cord',
    'theme_kept': copied_settings.get('theme') == 'amoled',
    'token_mode': oct(stat.S_IMODE(os.stat(app.TOKEN_FILE).st_mode)),
    'settings_mode': oct(stat.S_IMODE(os.stat(app.SETTINGS_FILE).st_mode)),
    'marker': os.path.exists(app.MIGRATION_MARKER),
    'legacy_untouched': legacy_before == (digest(legacy_token), digest(legacy_settings)),
}

# 2. logout (credenciais apagadas) nao pode restaurar a credencial antiga
os.remove(app.TOKEN_FILE)
app.migrate_legacy_config()
after_logout = {'token_absent': not os.path.exists(app.TOKEN_FILE)}

# 3. save_token e log criam arquivos 0600
app.save_token('fake-new-credential')
token_mode = oct(stat.S_IMODE(os.stat(app.TOKEN_FILE).st_mode))
clog.set_verbose(True)
clog.log('cmd=send canal=100 chars=3')
log_mode = oct(stat.S_IMODE(os.stat(clog.LOG_FILE).st_mode))

# 4. atualizacoes concorrentes de configuracao: sem erro e sem perder chaves
shared = {'name': '4Cord'}
errors = []
start = threading.Barrier(9)

def worker(n):
    try:
        start.wait()
        for i in range(120):
            app.update_settings(shared, **{f'k{n}_{i}': i})
    except Exception as e:
        errors.append((type(e).__name__, str(e)))

threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
for t in threads:
    t.start()
start.wait()
for t in threads:
    t.join()
with open(app.SETTINGS_FILE, encoding='utf-8') as fh:
    disk = json.load(fh)
concurrent = {
    'errors': errors[:3],
    'error_count': len(errors),
    'keys_in_memory': len(shared),
    'keys_on_disk': len(disk),
    'all_present': all(f'k{n}_{i}' in disk for n in range(8) for i in range(120)),
    'settings_mode': oct(stat.S_IMODE(os.stat(app.SETTINGS_FILE).st_mode)),
}

# 5. save_settings com dicionario mutado por outra thread nao deve estourar
mut = {'name': '4Cord'}
mut_errors = []
stop = threading.Event()

def mutator():
    i = 0
    while not stop.is_set():
        mut[f'm{i}'] = i
        if i > 200:
            mut.pop(f'm{i-200}', None)
        i += 1

mt = threading.Thread(target=mutator)
mt.start()
try:
    for _ in range(300):
        try:
            app.save_settings(mut)
        except Exception as e:
            mut_errors.append((type(e).__name__, str(e)))
            break
finally:
    stop.set()
    mt.join()
mutated = {'errors': mut_errors[:3], 'error_count': len(mut_errors)}

print('MIGRATION', json.dumps(migrated, sort_keys=True))
print('AFTER_LOGOUT', json.dumps(after_logout, sort_keys=True))
print('MODES', json.dumps({'token': token_mode, 'log': log_mode}, sort_keys=True))
print('CONCURRENT', json.dumps(concurrent, sort_keys=True))
print('MUTATED_DICT', json.dumps(mutated, sort_keys=True))
