const UPSTREAM = "https://sql-copilot-frontend.singhshasank50.workers.dev";

/**
 * Gives the application a Pages hostname that can be used as a CNAME target
 * for third-party subdomain services such as is-a.dev. The application itself
 * remains served by the production OpenNext Worker.
 */
export const onRequest: PagesFunction = async ({ request }) => {
  const incomingUrl = new URL(request.url);
  const upstreamUrl = new URL(UPSTREAM);

  incomingUrl.protocol = upstreamUrl.protocol;
  incomingUrl.hostname = upstreamUrl.hostname;
  incomingUrl.port = upstreamUrl.port;

  return fetch(new Request(incomingUrl, request));
};
