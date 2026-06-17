import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const publicRoutes = ["/login", "/signup", "/forgot-password", "/reset-password"];

function externalUrl(request: NextRequest, pathname: string) {
  const url = request.nextUrl.clone();
  const forwardedHost = request.headers.get("x-forwarded-host");
  const host = forwardedHost ?? request.headers.get("host");
  const protocol = request.headers.get("x-forwarded-proto");
  url.pathname = pathname;
  url.search = "";
  if (host) url.host = host;
  if (protocol === "http" || protocol === "https") url.protocol = `${protocol}:`;
  return url;
}

export function middleware(request: NextRequest) {
  const path = request.nextUrl.pathname;
  const authenticated = request.cookies.has("sql_copilot_access");
  const isPublic = publicRoutes.some((route) => path === route || path.startsWith(`${route}/`));

  if (!authenticated && !isPublic) {
    const loginUrl = externalUrl(request, "/login");
    loginUrl.searchParams.set("next", path);
    return NextResponse.redirect(loginUrl);
  }

  if (authenticated && isPublic) {
    return NextResponse.redirect(externalUrl(request, "/dashboard"));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"]
};
