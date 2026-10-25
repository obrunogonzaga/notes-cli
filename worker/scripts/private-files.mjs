import { constants } from 'node:fs';
import { lstat, open, realpath } from 'node:fs/promises';
import { dirname, isAbsolute, resolve } from 'node:path';

export async function privateDirectory(path) {
  if (!isAbsolute(path) || resolve(path) !== path || await realpath(path) !== path) throw new Error('private_path');
  const stat = await lstat(path);
  if (!stat.isDirectory() || stat.uid !== process.geteuid() || (stat.mode & 0o777) !== 0o700) throw new Error('private_directory');
}

export async function readPrivateFile(path, maxBytes = 16384) {
  await privateDirectory(dirname(path));
  const file = await open(path, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  try {
    const stat = await file.stat();
    if (!stat.isFile() || stat.uid !== process.geteuid() || ![0o400, 0o600].includes(stat.mode & 0o777) || stat.size > maxBytes) throw new Error('private_file');
    const bytes = Buffer.alloc(maxBytes + 1);
    const { bytesRead } = await file.read(bytes);
    if (bytesRead > maxBytes) throw new Error('file_limit');
    return new TextDecoder('utf-8', { fatal: true }).decode(bytes.subarray(0, bytesRead));
  } finally { await file.close(); }
}

export async function writeNewPrivateFile(path, content) {
  await privateDirectory(dirname(path));
  const file = await open(path, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | constants.O_NOFOLLOW, 0o600);
  try {
    await file.writeFile(content, 'utf8');
    await file.sync();
  } finally { await file.close(); }
}

export async function readInput(path) {
  if (path !== '-') return readPrivateFile(path);
  if (process.stdin.isTTY) throw new Error('stdin_must_be_redirected');
  const chunks = [];
  let length = 0;
  for await (const chunk of process.stdin) {
    length += chunk.length;
    if (length > 16384) throw new Error('input_limit');
    chunks.push(chunk);
  }
  return new TextDecoder('utf-8', { fatal: true }).decode(Buffer.concat(chunks));
}
