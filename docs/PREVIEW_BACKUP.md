# Back up and restore preview data

The preview manager can save and restore the managed preview's application database. These commands require the managed preview to be stopped. They use the same exclusive process lock as install and rollback; stop a managed run with Ctrl+C before continuing.

Backups are local ZIP files under `<root>/backups`. A snapshot contains only `data/timers.sqlite3`, including timer, alarm, and shopping state. It excludes credentials, Home Assistant data, models, photos, and arbitrary folders. Keep the root and its backups private. They contain private application data and must never be uploaded for support or included in a public release.

## Create and list backups

Create a snapshot:

```sh
python -m tools.preview_install backup --root /tmp/alltron-preview
```

PowerShell:

```powershell
python -m tools.preview_install backup --root C:\AlltronPreview
```

List available backups:

```sh
python -m tools.preview_install backups --root /tmp/alltron-preview
```

PowerShell:

```powershell
python -m tools.preview_install backups --root C:\AlltronPreview
```

Each backup records an ID, kind (`snapshot` or `preserved-original`), creation time, active release SHA-256, database SHA-256, and database size. Metadata contains no row labels. The manager preserves existing data before an update or code rollback changes the selected release. It normally creates a validated snapshot. If the current database is corrupt or has an unsupported schema, it preserves the raw main file instead, provided there are no SQLite sidecars. This permits selecting recovery code even when current data needs repair. Storage, timeout, or other backup failures stop the code change. The command reports the backup kind and ID; `preserved-original` is not a validated snapshot.

## Restore a snapshot

Use the local 32-character lowercase hexadecimal backup ID from the listing. Select code whose release SHA-256 exactly matches the backup's recorded release SHA-256 before restoring. The source checksum check binds a backup to its release; code rollback remains a separate operation.

```sh
python -m tools.preview_install restore --root /tmp/alltron-preview --backup 0123456789abcdef0123456789abcdef --replace-data
```

PowerShell:

```powershell
python -m tools.preview_install restore --root C:\AlltronPreview --backup 0123456789abcdef0123456789abcdef --replace-data
```

The explicit `--replace-data` flag is required. Before changing data, the manager validates the backup checksum, database schema, and SQLite integrity, and requires that no SQLite sidecar files are present. It preserves the current original first: as a normal safety snapshot if the database is readable, or as a `preserved-original` ZIP containing the raw database if it is unreadable. A preserved-original archive is for recovery or inspection; it is not a normal restore source. Restore reports the safety backup ID. Database replacement is atomic.

Restoring rewinds application state only; it does not restore code. Restored alarms and timers may become active again, so review the restored state in the preview before relying on it.

The application uses SQLite's DELETE journal mode. Backups can capture committed WAL data, but restore refuses sidecars both before and after its safety snapshot. SQLite read-only access can create WAL/SHM sidecars for a database previously put in WAL mode, even after other users stop. In that case, restore stops without replacing the main file and may leave a new safety backup. A SQLite maintenance tool must checkpoint the database and switch it to DELETE journal mode before retrying. Do not manually delete WAL, SHM or journal files; they may hold state needed for recovery. Automated journal-mode repair is outside this preview.

## Limits and errors

Manual backup rejects missing, corrupt, oversized, or schema-mismatched databases. Restore rejects invalid snapshots and any current SQLite sidecars. Only the current-original preservation step allows the raw-file fallback described above. The limit is 64 MiB per database; snapshots use SQLite's backup API to include committed WAL data. Stop all database users, including unmanaged tools, before recovery; the manager's lock excludes only managed operations. Errors do not include database contents. State migration is not supported. Backups protect against ordinary application changes, not disk failure; keep any additional copy private and separate if you need off-device protection. There is no retention/pruning policy yet. Home Assistant accounts and data are not backed up. This developer preview provides no service or Raspberry Pi support. Windows folder ACLs are not audited; use fictional data on a trusted single-user desktop.
