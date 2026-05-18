export default {
  async fetch(request, env, ctx) {
    return new Response("OK");
  },
  async scheduled(event, env, ctx) {
    const url = "https://five-million-agent-3.onrender.com/health";
    try {
      await fetch(url, { method: "GET", signal: AbortSignal.timeout(10000) });
    } catch (e) {
      // Fire-and-forget, no action needed
    }
  }
};
