/**
 * hooks/usePlatformBoot.ts
 *
 * Orchestrates the platform boot sequence, updating BootState after each stage.
 * Runs once on mount. Uses sessionStorage to skip re-boot within same tab session.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import type { BootState } from '../types/demo';

const SESSION_KEY = 'kratos_booted';

interface BootStageConfig {
  stage: BootState['stage'];
  message: string;
  endpoint?: string;
  minDuration: number;
}

const BOOT_STAGES: BootStageConfig[] = [
  {
    stage: 'CONNECTING',
    message: 'Connecting to CauseLink engine...',
    endpoint: '/demo/health',
    minDuration: 400,
  },
  {
    stage: 'LOADING_SCENARIOS',
    message: 'Loading 3 scenario packs...',
    endpoint: '/demo/scenarios',
    minDuration: 500,
  },
  {
    stage: 'LOADING_CSV',
    message: 'Indexing 6,006 account records...',
    endpoint: '/demo/data/summary',
    minDuration: 600,
  },
  {
    stage: 'SEEDING_ONTOLOGY',
    message: 'Seeding CauseLink CanonGraph — 19 node labels, 26 rel-types...',
    endpoint: '/demo/ontology/status',
    minDuration: 700,
  },
  {
    stage: 'READY',
    message: 'Platform ready',
    minDuration: 300,
  },
];

const INITIAL_BOOT_STATE: BootState = {
  stage: 'CONNECTING',
  message: 'Connecting to CauseLink engine...',
  scenariosLoaded: 0,
  recordsLoaded: 0,
  nodesSeeded: 0,
  elapsed: 0,
  completedStages: 0,
  stageTimings: {},
};

const delay = (ms: number): Promise<void> =>
  new Promise((resolve) => setTimeout(resolve, ms));

export function usePlatformBoot(): {
  bootState: BootState;
  isBooting: boolean;
  retryBoot: () => void;
} {
  const [bootState, setBootState] = useState<BootState>(INITIAL_BOOT_STATE);
  const [isBooting, setIsBooting] = useState(true);
  const startTimeRef = useRef<number>(Date.now());
  const runCountRef = useRef<number>(0);

  const runBoot = useCallback(async () => {
    const runId = ++runCountRef.current;
    startTimeRef.current = Date.now();

    setIsBooting(true);
    setBootState({ ...INITIAL_BOOT_STATE });

    let scenariosLoaded = 0;
    let recordsLoaded = 0;
    let nodesSeeded = 0;
    const timings: Partial<Record<BootState['stage'], number>> = {};

    for (let i = 0; i < BOOT_STAGES.length; i++) {
      if (runCountRef.current !== runId) return; // stale run

      const cfg = BOOT_STAGES[i];
      const stageStart = Date.now();

      setBootState((prev) => ({
        ...prev,
        stage: cfg.stage,
        message: cfg.message,
        elapsed: Date.now() - startTimeRef.current,
      }));

      try {
        // Run fetch + minimum duration in parallel
        const tasks: Array<Promise<unknown>> = [delay(cfg.minDuration)];
        if (cfg.endpoint) {
          tasks.push(
            fetch(cfg.endpoint).then((r) => {
              if (!r.ok) throw new Error(`HTTP ${r.status} from ${cfg.endpoint}`);
              return r.json();
            })
          );
        }

        const results = await Promise.allSettled(tasks);

        // Check for fetch failure
        const fetchResult = cfg.endpoint ? results[1] : null;
        if (fetchResult && fetchResult.status === 'rejected') {
          throw new Error(fetchResult.reason instanceof Error
            ? fetchResult.reason.message
            : String(fetchResult.reason));
        }

        // Parse results for specific stages
        if (cfg.endpoint && fetchResult?.status === 'fulfilled') {
          const data = fetchResult.value as Record<string, unknown>;

          if (cfg.stage === 'LOADING_SCENARIOS') {
            const total = typeof data.total === 'number' ? data.total : 0;
            scenariosLoaded = total;
          }

          if (cfg.stage === 'LOADING_CSV') {
            const total = typeof data.total_records === 'number' ? data.total_records : 6006;
            recordsLoaded = total;
          }

          if (cfg.stage === 'SEEDING_ONTOLOGY') {
            const n = typeof data.nodes === 'number' ? data.nodes : 18;
            nodesSeeded = n;
          }
        }

        if (runCountRef.current !== runId) return;

        const stageMs = Date.now() - stageStart;
        timings[cfg.stage] = stageMs;

        setBootState((prev) => ({
          ...prev,
          completedStages: i + 1,
          scenariosLoaded,
          recordsLoaded,
          nodesSeeded,
          elapsed: Date.now() - startTimeRef.current,
          stageTimings: { ...prev.stageTimings, [cfg.stage]: stageMs },
        }));
      } catch (err) {
        if (runCountRef.current !== runId) return;

        const msg = err instanceof Error ? err.message : String(err);
        setBootState((prev) => ({
          ...prev,
          stage: 'FAILED',
          message: 'Boot failed',
          error: msg,
          elapsed: Date.now() - startTimeRef.current,
        }));
        setIsBooting(false);
        return;
      }
    }

    if (runCountRef.current !== runId) return;

    // Final READY state
    setBootState((prev) => ({
      ...prev,
      stage: 'READY',
      message: 'Platform ready',
      elapsed: Date.now() - startTimeRef.current,
    }));

    // Mark session as booted
    try {
      sessionStorage.setItem(SESSION_KEY, '1');
    } catch {
      // sessionStorage unavailable — ignore
    }

    // Small delay before hiding overlay
    await delay(400);
    if (runCountRef.current === runId) {
      setIsBooting(false);
    }
  }, []);

  const retryBoot = useCallback(() => {
    try {
      sessionStorage.removeItem(SESSION_KEY);
    } catch {
      // ignore
    }
    void runBoot();
  }, [runBoot]);

  useEffect(() => {
    // Skip boot if already completed this session
    try {
      if (sessionStorage.getItem(SESSION_KEY) === '1') {
        setBootState((prev) => ({
          ...prev,
          stage: 'READY',
          message: 'Platform ready',
          completedStages: BOOT_STAGES.length,
          recordsLoaded: 6006,
          scenariosLoaded: 3,
          nodesSeeded: 18,
        }));
        setIsBooting(false);
        return;
      }
    } catch {
      // sessionStorage unavailable — run boot anyway
    }

    void runBoot();
  }, [runBoot]);

  return { bootState, isBooting, retryBoot };
}
