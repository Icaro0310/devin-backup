# devin-backup

> **Projeto comunitário não oficial.** Sem afiliação, endosso ou patrocínio da
> Cognition AI. "Devin" é marca registada da Cognition AI.

**[English](README.md)** · Português (BR)

Backup & restore seguro dos stores do Devin Desktop: snapshots com timestamp
da `sessions.db`, `acp-messages/`, `state.vscdb` e da config `.devin/` — com
cópia consistente de SQLite, verificação de integridade e rotação.

## O problema

Tudo o que o Devin guarda sobre o teu trabalho vive numa mão-cheia de bases
SQLite locais e ficheiros de config. Dois modos de falha tornam perigoso um
backup na base do `copy`/`robocopy`:

1. **Ficheiros SQLite vivos.** Copiar a `sessions.db` com o Devin a correr
   pode produzir uma cópia corrompida — páginas a meio de escrita, WAL por
   fazer merge. A cópia *parece* boa até ao dia em que a restauras.
2. **Drift de schema silencioso.** A `sessions.db` já passou por **17
   migrações**. Restaurar um backup antigo por cima de uma instalação mais
   nova faz downgrade dos teus dados em silêncio; nada te avisa.

## Trabalho anterior (prior art)

Ferramentas de backup genéricas — `restic`, `borg`, `robocopy`, Histórico de
Ficheiros do Windows — copiam bytes com fidelidade, mas não sabem nada de
consistência SQLite nem de que ficheiros num data dir do Devin realmente
importam. Este projeto adapta a prática standard (online backup API do
`sqlite3` + manifest com checksums + rotação por retenção); não reinventa a
roda.

## O que o torna Devin-native

*Sabe que stores são o cérebro do Devin — e avisa quando o formato desse
cérebro mudou por baixo de um backup.*

1. **Lado a lado:** os snapshots são feitos via `sqlite3.Connection.backup()`
   (consistente mesmo com o Devin a correr, com fallback para cópia simples),
   e cada manifest regista `schema_version` via
   [`devin-internals-spec`](https://github.com/Icaro0310/devin-internals-spec).
2. **Sem Devin:** tira o Devin e não há nada para descobrir — o extra
   desaparece.
3. **Uma frase:** no restore recebes *"o backup é v15, o atual é v17"* em vez
   de um downgrade silencioso.

## Instalação

Requer Python ≥ 3.10 e `pipx`. **Windows (PowerShell):** instale `pipx` com `py -m pip install --user pipx`, execute `py -m pipx ensurepath` e reabra o terminal. **Linux (Debian/Ubuntu):** execute `sudo apt install pipx python3-venv` e `pipx ensurepath`; reabra o terminal. Noutras distribuições Linux, instale `pipx` pelo gestor de pacotes.

```bash
pipx install "devin-backup @ git+https://github.com/Icaro0310/devin-backup.git"
```

(Ainda não está no PyPI.)

## Uso

```bash
devin-backup create  [--data-dir <raiz-dados>] [--config-dir <raiz-config-ui>] [--out <backups-dir>]
devin-backup verify  <snapshot-dir>
devin-backup list    [--out <backups-dir>]
devin-backup restore <snapshot-dir> --to <raiz-dados> [--config-to <raiz-config-ui>] [--apply] [--no-backup]
devin-backup rotate  [--keep N] --yes
```

- `create` guarda `sessions.db`, bases ACP, `state.vscdb` e ficheiros `.devin/`
  quando presentes. O manifesto v2 regista a raiz de origem de cada ficheiro;
  snapshots v1 antigos continuam legíveis.
- No Linux, a raiz de dados e a raiz de configuração da UI são separadas. O
  `create` padrão deteta ambas. Se passares `--data-dir`, passa também
  `--config-dir` para incluir os stores da UI.
- `verify` re-verifica hashes e corre `PRAGMA integrity_check` nas bases;
  exit code 1 em caso de falha.
- `restore` é **dry-run por defeito**. Restaura dados em `--to` e ficheiros de
  UI em `--config-to` (por omissão, a raiz de configuração detetada). Passa
  `--apply` para escrever. Antes de sobrescrever, cria backup
  `pre-restore-<ts>`; `--no-backup` recusa sobrescritas.
- `rotate` mantém os N snapshots mais recentes (default `$DEVIN_BACKUP_KEEP`
  ou 10) e não faz nada sem `--yes`. Diretórios `pre-restore-*` nunca são
  rodados.

Defaults: a raiz de sessões é `$DEVIN_DATA_DIR` ou `%APPDATA%\\devin` no Windows
e `$XDG_DATA_HOME/devin` (normalmente `~/.local/share/devin`) no Linux. A raiz
de configuração UI é `%APPDATA%\\Devin` no Windows e
`$XDG_CONFIG_HOME/Devin` (normalmente `~/.config/Devin`) no Linux. `--out`
usa `$DEVIN_BACKUP_DIR` ou `<raiz-dados>/backups`.

```python
from devin_backup import snapshot, verify, restore

snap = snapshot.create_snapshot(data_dir, backups_dir, config_dir=config_dir)
verify.verify_snapshot(snap)                            # {"ok": True, ...}
restore.restore_snapshot(snap, data_dir, config_dir=config_dir)  # dry-run
```

## Funciona só com o Devin (modo Devin-only)

O devin-backup copia as stores locais do Devin para uma pasta de destino à
tua escolha — disco externo, pasta sincronizada, qualquer sítio em disco. Sem
conta cloud, VM ou serviço de rede.

Os snapshots contêm dados reais de sessão (prompts, caminhos, comandos).
Trata o destino do backup como sensível: mantém-no num volume privado ou
cifrado e aplica o mesmo cuidado que dás às stores originais.

## Suporte de plataformas

Testado em **Windows e Linux** (CI em `windows-latest` + `ubuntu-latest`). No
Windows os stores partilham `%APPDATA%\\Devin`. No Linux são detetados em
`XDG_DATA_HOME/devin` e `XDG_CONFIG_HOME/Devin`. Usa `--data-dir` e
`--config-dir` para caminhos personalizados.

## Limitações

- **Internals privados e voláteis.** Estes stores são detalhe de
  implementação do Devin; paths e schemas podem mudar em qualquer release. A
  descoberta de stores é por padrões (`*.db`, `*.vscdb`, `.devin/`), best-effort.
- **Versões de schema só existem onde o Devin guarda o ledger** — a
  `sessions.db` tem `schema_version` real; `acp-messages`/`state.vscdb` não
  têm nenhuma para registar.
- **Não é um scheduler.** O M1 tira snapshots quando o corres; integração com
  Task Scheduler / cron está na fila do M2 (vê `docs/SPEC.md` §10).
- **Só escreve com `--apply`.** O backup nunca toca nas bases do Devin senão
  pela backup API read-only. `restore --apply` é o único caminho de escrita e
  é sempre protegido por um backup pre-restore.
- Testado apenas contra **fixtures sintéticas** — conteúdo real de sessões
  nunca é copiado, por desenho.

## Desenvolvimento

```bash
pip install -e ".[dev]"
python -m pytest
```

Regras base em [CONTRIBUTING.md](CONTRIBUTING.md): fixtures antes de código,
commits pequenos, docs bilingues. Spec canónica: [docs/SPEC.md](docs/SPEC.md).

## Licença

MIT — vê [LICENSE](LICENSE).
