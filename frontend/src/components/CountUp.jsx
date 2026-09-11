// Adapted from React Bits' "CountUp" (https://reactbits.dev/text-animations/count-up),
// kept close to upstream. Built on `motion/react`'s spring-driven value, animating a
// <span>'s textContent directly rather than through React state on every tick.
import { useInView, useMotionValue, useSpring } from "motion/react";
import { useCallback, useEffect, useRef } from "react";

export default function CountUp({
  to,
  from = 0,
  direction = "up",
  delay = 0,
  duration = 1,
  className = "",
  startWhen = true,
  separator = ",",
}) {
  const ref = useRef(null);
  const motionValue = useMotionValue(direction === "down" ? to : from);

  const damping = 20 + 40 * (1 / duration);
  const stiffness = 100 * (1 / duration);

  const springValue = useSpring(motionValue, { damping, stiffness });
  const isInView = useInView(ref, { once: true, margin: "0px" });

  const getDecimalPlaces = (num) => {
    const str = num.toString();
    if (str.includes(".")) {
      const decimals = str.split(".")[1];
      if (parseInt(decimals, 10) !== 0) return decimals.length;
    }
    return 0;
  };

  const maxDecimals = Math.max(getDecimalPlaces(from), getDecimalPlaces(to));

  const formatValue = useCallback(
    (latest) => {
      const hasDecimals = maxDecimals > 0;
      const options = {
        useGrouping: !!separator,
        minimumFractionDigits: hasDecimals ? maxDecimals : 0,
        maximumFractionDigits: hasDecimals ? maxDecimals : 0,
      };
      const formatted = Intl.NumberFormat("en-US", options).format(latest);
      return separator ? formatted.replace(/,/g, separator) : formatted;
    },
    [maxDecimals, separator]
  );

  useEffect(() => {
    if (ref.current) {
      ref.current.textContent = formatValue(direction === "down" ? to : from);
    }
  }, [from, to, direction, formatValue]);

  useEffect(() => {
    if (isInView && startWhen) {
      const timeoutId = setTimeout(() => {
        motionValue.set(direction === "down" ? from : to);
      }, delay * 1000);
      return () => clearTimeout(timeoutId);
    }
  }, [isInView, startWhen, motionValue, direction, from, to, delay]);

  useEffect(() => {
    const unsubscribe = springValue.on("change", (latest) => {
      if (ref.current) {
        ref.current.textContent = formatValue(latest);
      }
    });
    return () => unsubscribe();
  }, [springValue, formatValue]);

  return <span className={className} ref={ref} />;
}
