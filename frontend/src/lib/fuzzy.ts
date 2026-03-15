import type { PersonResult } from './api';

/**
 * Lightweight JS port of fuzzywuzzy's token_set_ratio (0–100).
 * Shared by all pages that need fuzzy name matching.
 */
export function tokenSetRatio(a: string, b: string): number {
	const tokenise = (s: string) =>
		s.toLowerCase().replace(/[^a-z0-9\s]/g, '').split(/\s+/).filter(Boolean);
	const setA = new Set(tokenise(a));
	const setB = new Set(tokenise(b));
	const inter = [...setA].filter(t => setB.has(t));
	const onlyA = [...setA].filter(t => !setB.has(t));
	const onlyB = [...setB].filter(t => !setA.has(t));
	const sorted = (arr: string[]) => [...arr].sort().join(' ');
	const s0 = sorted(inter);
	const s1 = [s0, sorted(onlyA)].filter(Boolean).join(' ');
	const s2 = [s0, sorted(onlyB)].filter(Boolean).join(' ');
	function ratio(x: string, y: string) {
		if (!x && !y) return 100;
		if (!x || !y) return 0;
		let matches = 0;
		const shorter = x.length <= y.length ? x : y;
		const longer  = x.length <= y.length ? y : x;
		const used = new Array(longer.length).fill(false);
		for (let i = 0; i < shorter.length; i++) {
			for (let j = 0; j < longer.length; j++) {
				if (!used[j] && shorter[i] === longer[j]) { matches++; used[j] = true; break; }
			}
		}
		return Math.round((2 * matches / (shorter.length + longer.length)) * 100);
	}
	return Math.max(ratio(s0, s0), ratio(s1, s2), ratio(s0, s1), ratio(s0, s2));
}

export interface Cluster {
	primary: PersonResult;
	members: PersonResult[];
}

/**
 * Groups search results into clusters by fuzzy name similarity.
 * Items within `threshold`% of a cluster's primary name are merged.
 */
export function clusterResults(items: PersonResult[], threshold: number): Cluster[] {
	const clusters: Cluster[] = [];
	for (const item of items) {
		let placed = false;
		for (const cluster of clusters) {
			if (tokenSetRatio(item.name, cluster.primary.name) >= threshold) {
				cluster.members.push(item); placed = true; break;
			}
		}
		if (!placed) clusters.push({ primary: item, members: [item] });
	}
	return clusters;
}
