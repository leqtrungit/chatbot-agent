import { NextRequest, NextResponse } from "next/server";

const AUTH_COOKIE_NAME = "admin_auth";

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const hasAuth = Boolean(request.cookies.get(AUTH_COOKIE_NAME)?.value);

  if (pathname === "/login") {
    return NextResponse.next();
  }

  if (!hasAuth) {
    const loginUrl = new URL("/login", request.url);
    return NextResponse.redirect(loginUrl);
  }

  if (pathname === "/") {
    return NextResponse.redirect(new URL("/domains", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/", "/domains/:path*", "/api-keys/:path*", "/login"],
};
