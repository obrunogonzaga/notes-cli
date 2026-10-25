import { parseToken, tokenVerifier } from './token';

const authenticated = Symbol('authenticated');
export interface AuthenticatedIdentity {
  readonly [authenticated]: true;
  readonly identity: Readonly<{ id: string; name: string }>;
  readonly credentialId: string;
}

function digestBytes(hex: string): Uint8Array {
  return Uint8Array.from(hex.match(/../g)!, (byte) => Number.parseInt(byte, 16));
}

// Uma consulta ao primário por tentativa; nenhum cache, token ou digest no contexto.
// Falhas D1 propagam ao boundary HTTP, que retorna 503 sem diagnóstico interno.
export async function authenticate(request: Request, db: D1Database): Promise<AuthenticatedIdentity | null> {
  const header = request.headers.get('Authorization');
  const match = header?.match(/^Bearer ([^\s,]+)$/i);
  if (!match) return null;
  const token = match[1]!;
  const parsed = parseToken(token);
  if (!parsed) return null;
  const row = await db.prepare(`
    SELECT c.identity_id, c.verifier_sha256, c.revoked_at, i.name, i.disabled_at
    FROM credentials c JOIN identities i ON i.id = c.identity_id
    WHERE c.id = ?
  `).bind(parsed.credentialId).first<{
    identity_id: string; verifier_sha256: string; revoked_at: string | null;
    name: string; disabled_at: string | null;
  }>();
  const digest = await tokenVerifier(token);
  const validVerifier = !!row && /^[0-9a-f]{64}$/.test(row.verifier_sha256);
  // Sempre comparar dois digests de 32 bytes, inclusive para ID ausente/digest corrompido.
  const equal = crypto.subtle.timingSafeEqual(
    digestBytes(digest), digestBytes(validVerifier ? row.verifier_sha256 : '0'.repeat(64)),
  );
  if (!row || !validVerifier || !equal || row.identity_id !== parsed.identityId ||
      row.revoked_at !== null || row.disabled_at !== null) return null;
  return Object.freeze({
    [authenticated]: true as const,
    identity: Object.freeze({ id: row.identity_id, name: row.name }),
    credentialId: parsed.credentialId,
  });
}

// A autoria não recebe payload, author, destinatário ou escopo do cliente.
export function authenticatedAuthor(auth: AuthenticatedIdentity): Readonly<{ id: string; name: string }> {
  return auth.identity;
}

// Incorporar SQL + bindings em cada INSERT/UPDATE no mesmo batch que grava dados.
// Um SELECT anterior, mesmo authenticate(), não substitui esta condição no commit.
export function activeCredentialGuard(auth: AuthenticatedIdentity): { sql: string; bindings: string[] } {
  return {
    sql: `EXISTS (SELECT 1 FROM credentials auth_c JOIN identities auth_i ON auth_i.id = auth_c.identity_id
      WHERE auth_c.id = ? AND auth_c.identity_id = ? AND auth_c.revoked_at IS NULL AND auth_i.disabled_at IS NULL)`,
    bindings: [auth.credentialId, auth.identity.id],
  };
}

// Selecionar no mesmo batch/snapshot para dar precedência a 401 sobre replay/conflito.
export function activeCredentialStatement(db: D1Database, auth: AuthenticatedIdentity): D1PreparedStatement {
  const guard = activeCredentialGuard(auth);
  return db.prepare(`SELECT ${guard.sql} AS active`).bind(...guard.bindings);
}
