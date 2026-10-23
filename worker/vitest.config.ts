import { cloudflareTest, readD1Migrations } from '@cloudflare/vitest-plugin';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [cloudflareTest({
    wrangler: { configPath: './wrangler.jsonc' },
    remoteBindings: false,
    miniflare: {
      d1Databases: { DB: 'notes-integration-only' },
      bindings: { TEST_MIGRATIONS: await readD1Migrations('./migrations') },
    },
  })],
  test: { include: ['test/**/*.test.ts'] },
});
