"use client";

import { usePathname } from "next/navigation";
import { useApi } from "@/lib/hooks";

/** The unread count beside the Notifications link. Refetches on every navigation. */
export default function UnreadBadge() {
  const page = usePathname();
  const { data } = useApi<{ unread: number }>(`/notifications/summary?page=${encodeURIComponent(page)}`);
  const n = data?.unread ?? 0;
  if (n === 0) return null;
  return (
    <span className="ml-auto flex min-w-5 items-center justify-center rounded-full bg-rose-600 px-1.5 text-[11px] font-semibold leading-5 text-white" aria-label={`${n} unread`}>
      {n > 99 ? "99+" : n}
    </span>
  );
}
