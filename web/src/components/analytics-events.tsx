"use client";

import { useEffect } from "react";
import { track } from "@vercel/analytics";

export function AnalyticsEvents() {
  useEffect(() => {
    function onClick(event: MouseEvent) {
      const target = event.target;
      if (!(target instanceof Element)) return;

      const link = target.closest<HTMLElement>("[data-analytics-event]");
      const eventName = link?.dataset.analyticsEvent;
      if (!eventName) return;

      track(eventName, {
        href: link instanceof HTMLAnchorElement ? link.href : undefined,
      });
    }

    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, []);

  return null;
}
