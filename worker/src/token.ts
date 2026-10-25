// Compartilhado pelo Worker e pelo operador Node; nenhum segredo é persistido aqui.
export const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const SECRET = /^[A-Za-z0-9_-]{42}[AEIMQUYcgkosw048]$/;

export function parseToken(token: string): { identityId: string; credentialId: string } | null {
  if (token.length !== 121) return null;
  const parts = token.split('.');
  if (parts.length !== 4 || parts[0] !== 'nt1' ||
      !UUID_V4.test(parts[1]!) || !UUID_V4.test(parts[2]!) || !SECRET.test(parts[3]!)) return null;
  return { identityId: parts[1]!, credentialId: parts[2]! };
}

export async function tokenVerifier(token: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(token));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
}

export function generateToken(identityId: string): { token: string; credentialId: string } {
  if (!UUID_V4.test(identityId)) throw new Error('UUID de identidade inválido.');
  const credentialId = crypto.randomUUID();
  const secret = crypto.getRandomValues(new Uint8Array(32));
  const encoded = btoa(String.fromCharCode(...secret)).replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/, '');
  return { token: `nt1.${identityId}.${credentialId}.${encoded}`, credentialId };
}
