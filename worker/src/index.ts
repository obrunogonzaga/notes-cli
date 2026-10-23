// Apenas infraestrutura. As rotas de negócio /v1 serão entregues em #9–#11/#14.
export default {
  async fetch(request, env): Promise<Response> {
    const requestId = crypto.randomUUID();
    const headers = {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store',
      'X-Request-ID': requestId,
    };
    const reply = (status: number, payload: object, extraHeaders = {}) =>
      Response.json(
        { api: 'notes-remote', schema_version: 1, request_id: requestId, ...payload },
        { status, headers: { ...headers, ...extraHeaders } },
      );

    if (new URL(request.url).pathname !== '/healthz') {
      return reply(404, {
        error: { code: 'not_found', message: 'Rota não encontrada.', retryable: false },
      });
    }
    if (request.method !== 'GET') {
      return reply(405, {
        error: { code: 'method_not_allowed', message: 'Método não permitido.', retryable: false },
      }, { Allow: 'GET' });
    }

    try {
      const global = await env.DB.prepare(
        "SELECT 1 AS ready FROM scopes WHERE id = 'global' AND kind = 'global' AND name = 'global' AND created_by IS NULL",
      ).first<{ ready: number }>();
      if (global?.ready === 1) return reply(200, { status: 'ready' });
    } catch {
      // Não expor SQL, stack, dados ou metadados do binding.
    }
    return reply(503, {
      error: { code: 'service_unavailable', message: 'Serviço indisponível.', retryable: true },
    });
  },
} satisfies ExportedHandler<Env>;
