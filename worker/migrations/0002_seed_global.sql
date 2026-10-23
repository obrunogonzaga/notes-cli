-- Global existe antes de provisionar identidades. Não contém credenciais.
INSERT INTO scopes(id, kind, name, created_at, created_by)
VALUES ('global', 'global', 'global', '2026-10-23T00:00:00.000Z', NULL);
