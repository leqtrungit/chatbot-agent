import { NextRequest, NextResponse } from "next/server";

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Allow login page
  if (pathname === "/login" || pathname === "/callback") {
    return NextResponse.next();
  }

  // Redirect home to domains
  if (pathname === "/") {
    return NextResponse.redirect(new URL("/domains", request.url));
  }

  // All other admin routes are protected client-side (token is in localStorage)
  return NextResponse.next();
}

export const config = {
  matcher: ["/", "/domains/:path*", "/agents/:path*", "/api-keys/:path*", "/login", "/callback"],
};
