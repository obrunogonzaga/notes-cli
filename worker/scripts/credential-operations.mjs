import { generateToken, tokenVerifier, UUID_V4 } from '../src/token.ts';

const fields = {
  create: ['operation', 'name', 'credential_file'],
  rotate: ['operation', 'identity_id', 'credential_file'],
  revoke: ['operation', 'credential_id'],
  disable: ['operation', 'identity_id'],
};

export function validateOperation(input) {
  if (!input || typeof input !== 'object' || Array.isArray(input) || !Object.hasOwn(fields, input.operation)) throw new Error('operation');
  const allowed = fields[input.operation];
  if (Object.keys(input).some((key) => !allowed.includes(key)) || allowed.some((key) => typeof input[key] !== 'string')) throw new Error('fields');
  if ('identity_id' in input && !UUID_V4.test(input.identity_id)) throw new Error('identity_id');
  if ('credential_id' in input && !UUID_V4.test(input.credential_id)) throw new Error('credential_id');
  if (input.operation === 'create' && (
    [...input.name].length < 1 || [...input.name].length > 128 ||
    /[\u0000-\u001f\u007f-\u009f\ud800-\udfff]/u.test(input.name) ||
    !/[^\p{White_Space}]/u.test(input.name)
  )) throw new Error('name');
}

// Retorna instruções parametrizadas; só o arquivo privado recebe o token.
export async function prepareOperation(input) {
  validateOperation(input);
  const now = new Date().toISOString();
  const identityId = input.operation === 'create' ? crypto.randomUUID() : input.identity_id;
  const issuance = ['create', 'rotate'].includes(input.operation) ? generateToken(identityId) : null;
  const credentialId = issuance?.credentialId ?? input.credential_id;
  const statements = [];
  if (input.operation === 'create') statements.push({
    sql: 'INSERT INTO identities(id, name, created_at) VALUES (?, ?, ?)',
    params: [identityId, input.name, now],
  });
  if (issuance) statements.push({
    sql: `INSERT INTO credentials(id, identity_id, verifier_sha256, created_at)
      SELECT ?, id, ?, ? FROM identities WHERE id = ? AND disabled_at IS NULL RETURNING id`,
    params: [credentialId, await tokenVerifier(issuance.token), now, identityId],
  });
  if (input.operation === 'revoke') statements.push({
    sql: 'UPDATE credentials SET revoked_at = COALESCE(revoked_at, ?) WHERE id = ? RETURNING id',
    params: [now, credentialId],
  });
  if (input.operation === 'disable') statements.push({
    sql: 'UPDATE identities SET disabled_at = COALESCE(disabled_at, ?) WHERE id = ? RETURNING id',
    params: [now, identityId],
  });
  return {
    token: issuance?.token,
    statements,
    result: { operation: input.operation, ...(identityId && { identity_id: identityId }), ...(credentialId && { credential_id: credentialId }) },
  };
}
