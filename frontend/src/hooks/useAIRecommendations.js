import { useCallback, useEffect, useState } from "react";

const EMPTY = { items: [], provider: null, generatedAt: null, stale: false };

function normalize(data) {
  return {
    items: data.items ?? [],
    provider: data.provider ?? null,
    generatedAt: data.generated_at ?? null,
    stale: Boolean(data.stale),
  };
}

/**
 * Loads AI recommendations for one page.
 *
 * The mount fetch never generates. It reads whatever was last written — which is
 * fast, free, and cannot hold the page behind a provider — and generation happens
 * only when the user asks for it. `isGenerating` is tracked separately from the
 * initial load so the panel can show a spinner on the button without blanking the
 * lines already on screen.
 *
 * State is only ever set from a promise continuation, never synchronously in the
 * effect body (react-hooks/set-state-in-effect).
 *
 * A failure here is never fatal. The endpoint falls back to rule-based lines when
 * no provider answers, so an error at this level means the request itself failed;
 * the panel shows its empty state and the rest of the page is unaffected.
 */
export function useAIRecommendations(fetcher) {
  const [state, setState] = useState(EMPTY);
  const [isLoading, setIsLoading] = useState(true);
  const [isGenerating, setIsGenerating] = useState(false);

  useEffect(() => {
    let cancelled = false;

    fetcher({ generate: false })
      .then((data) => {
        if (!cancelled) setState(normalize(data));
      })
      .catch((err) => {
        console.error("Failed to load AI recommendations:", err);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [fetcher]);

  const generate = useCallback(() => {
    setIsGenerating(true);
    return fetcher({ generate: true })
      .then((data) => setState(normalize(data)))
      .catch((err) => console.error("Failed to generate AI recommendations:", err))
      .finally(() => setIsGenerating(false));
  }, [fetcher]);

  return { ...state, isLoading, isGenerating, generate };
}

export default useAIRecommendations;
