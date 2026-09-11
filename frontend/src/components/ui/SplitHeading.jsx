/**
 * src/components/ui/SplitHeading.jsx
 *
 * One-time character reveal for a page's main heading, adapted from React
 * Bits' "SplitText" (GSAP + GSAP's SplitText plugin, via @gsap/react's
 * useGSAP). Simplified from upstream in two ways:
 *
 * - No gsap/ScrollTrigger: upstream's SplitText is built for scroll-into-view
 *   reveals on long marketing pages. Every call site in this app is a page
 *   heading that's already in the viewport on load, so it animates directly
 *   on mount instead of carrying a scroll-trigger dependency it doesn't need.
 * - Waits on `document.fonts.ready` before splitting (GSAP's own guidance for
 *   a custom webfont like Fraunces — splitting before the font swaps in
 *   mis-measures character widths and reflows visibly). This is the first
 *   use of the Font Loading API in this codebase.
 *
 * Renders the plain, unsplit text immediately under prefers-reduced-motion
 * (usePrefersReducedMotion, shared with Silk/CountUp/StaggerIn) rather than
 * running the reveal — same convention as the rest of this app's motion.
 */
import { useRef, useState, useEffect } from "react";
import { gsap } from "gsap";
import { SplitText as GSAPSplitText } from "gsap/SplitText";
import { useGSAP } from "@gsap/react";
import { usePrefersReducedMotion } from "../../hooks/usePrefersReducedMotion";

gsap.registerPlugin(GSAPSplitText, useGSAP);

export default function SplitHeading({ text, as: Tag = "h1", className = "", delay = 0.02, duration = 0.5 }) {
  const ref = useRef(null);
  const [fontsLoaded, setFontsLoaded] = useState(false);
  const prefersReducedMotion = usePrefersReducedMotion();

  useEffect(() => {
    // document.fonts.ready resolves on the next microtask even when the
    // fonts are already loaded, so there's no need to branch on .status —
    // this keeps the state update inside an async callback rather than the
    // effect body itself.
    document.fonts.ready.then(() => setFontsLoaded(true));
  }, []);

  useGSAP(
    () => {
      if (prefersReducedMotion || !ref.current || !fontsLoaded) return;
      const el = ref.current;

      const split = new GSAPSplitText(el, {
        type: "chars",
        smartWrap: true,
        charsClass: "split-char",
      });

      gsap.fromTo(
        split.chars,
        { opacity: 0, y: 16 },
        { opacity: 1, y: 0, duration, ease: "power3.out", stagger: delay }
      );

      return () => split.revert();
    },
    { dependencies: [text, fontsLoaded, prefersReducedMotion, delay, duration], scope: ref }
  );

  return (
    <Tag ref={ref} className={className}>
      {text}
    </Tag>
  );
}
