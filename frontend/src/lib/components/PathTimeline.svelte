<script lang="ts">
	import { onMount } from 'svelte';
	import * as d3 from 'd3';

	interface TLNode {
		id: string;
		type: 'person' | 'org';
		name: string;
		ministry?: string;
		agencyName?: string;
		isSource: boolean;
		isTarget: boolean;
		inPath: boolean;
		org_id?: number;
		person_id?: number;
	}
	interface TLEdge {
		source: string | TLNode;
		target: string | TLNode;
		inPath: boolean;
		yearLabel?: string;
	}
	interface Props {
		nodes: TLNode[];
		edges: TLEdge[];
		getMinistryColor: (m: string) => string;
	}
	let { nodes, edges, getMinistryColor }: Props = $props();

	let containerEl = $state<HTMLDivElement>();
	let W  = $state(900);
	let cH = $state(500);

	// Layout constants
	const LABEL_W    = 172;
	const GRP_H      = 22;
	const MIN_LANE_H = 30;
	const MAX_LANE_H = 80;
	const AXIS_H     = 42;
	const PAD_R      = 16;
	const BADGE_H    = 13;
	const CURRENT_YEAR = new Date().getFullYear();

	// Collapsible label state — Set of expanded agencyIds
	let expandedOrgs = $state(new Set<string>());
	function toggleOrg(agencyId: string) {
		const next = new Set(expandedOrgs);
		if (next.has(agencyId)) next.delete(agencyId); else next.add(agencyId);
		expandedOrgs = next;
	}

	// ── Helpers ─────────────────────────────────────────────────────────────────

	function eid(ep: string | TLNode): string {
		return typeof ep === 'string' ? ep : ep.id;
	}

	function parseYears(label: string): [number, number] | null {
		const parts = label.split(/[–—\-]/);
		const start = parseInt(parts[0].trim());
		if (isNaN(start)) return null;
		if (parts.length < 2) return [start, start + 1];
		const s = parts[1].trim();
		const end = !s || s === 'now' || s === 'present' ? CURRENT_YEAR : parseInt(s);
		return [start, isNaN(end) ? start + 1 : Math.max(end, start + 1)];
	}

	function initials(name: string) {
		return name.trim().split(/\s+/).map(w => w[0] ?? '').join('').slice(0, 2).toUpperCase();
	}

	function blockColor(n: TLNode): string {
		if (n.isSource) return '#2563eb';
		if (n.isTarget) return '#059669';
		return '#6366f1';
	}

	function trunc(s: string, max: number) {
		return s.length > max ? s.slice(0, max - 1) + '…' : s;
	}

	/**
	 * Parse an org agencyName into a hierarchy array.
	 * "MINISTRY OF COMM : DIVISION A : SUB-UNIT B" →
	 * if ministry = "MINISTRY OF COMM" → ["DIVISION A", "SUB-UNIT B"]
	 */
	function orgHierarchy(agencyName: string, ministry: string): string[] {
		let name = agencyName ?? '';
		// Strip ministry prefix (case-insensitive)
		const mu = ministry.toUpperCase();
		const nu = name.toUpperCase();
		if (nu.startsWith(mu)) {
			name = name.slice(ministry.length).replace(/^\s*:\s*/, '').trim();
		}
		return name.split(/\s*:\s*/).map(s => s.trim()).filter(Boolean);
	}

	// ── Block interface ──────────────────────────────────────────────────────────

	interface Block {
		personId: string;
		personName: string;
		initials: string;
		color: string;
		isSource: boolean;
		isTarget: boolean;
		ministry: string;
		agencyId: string;
		agencyName: string;
		yearStart: number;
		yearEnd: number;
		isFallback: boolean;
	}

	// ── Primary blocks (edges with yearLabel) ────────────────────────────────────

	const primaryBlocks = $derived.by((): Block[] => {
		const nm = new Map(nodes.map(n => [n.id, n]));
		const seen = new Set<string>();
		const out: Block[] = [];
		for (const e of edges) {
			if (!e.yearLabel) continue;
			const yr = parseYears(e.yearLabel);
			if (!yr) continue;
			const sid = eid(e.source), tid = eid(e.target);
			const sn = nm.get(sid), tn = nm.get(tid);
			if (!sn || !tn) continue;
			const person = sn.type === 'person' ? sn : tn;
			const org    = sn.type === 'org'    ? sn : tn;
			if (person.type !== 'person' || org.type !== 'org' || !org.ministry) continue;
			const key = `${person.id}::${org.id}`;
			if (seen.has(key)) continue;
			seen.add(key);
			out.push({
				personId: person.id, personName: person.name,
				initials: initials(person.name), color: blockColor(person),
				isSource: person.isSource, isTarget: person.isTarget,
				ministry: org.ministry, agencyId: org.id,
				agencyName: org.agencyName ?? org.name,
				yearStart: yr[0], yearEnd: yr[1], isFallback: false,
			});
		}
		return out;
	});

	const yr0 = $derived(
		primaryBlocks.length ? Math.min(...primaryBlocks.map(b => b.yearStart)) - 1 : 2015
	);
	const yr1 = $derived(
		primaryBlocks.length ? Math.max(...primaryBlocks.map(b => b.yearEnd))   + 1 : CURRENT_YEAR
	);

	// ── Fallback blocks for source/target without yearLabel ──────────────────────

	const blocks = $derived.by((): Block[] => {
		const nm = new Map(nodes.map(n => [n.id, n]));
		const out = [...primaryBlocks];
		const coveredPersons = new Set(out.map(b => b.personId));

		for (const n of nodes) {
			if (!n.inPath || (!n.isSource && !n.isTarget)) continue;
			if (coveredPersons.has(n.id)) continue;
			for (const e of edges) {
				if (!e.inPath) continue;
				const sid = eid(e.source), tid = eid(e.target);
				if (sid !== n.id && tid !== n.id) continue;
				const orgId = sid === n.id ? tid : sid;
				const org = nm.get(orgId);
				if (!org || org.type !== 'org' || !org.ministry) continue;
				out.push({
					personId: n.id, personName: n.name,
					initials: initials(n.name), color: blockColor(n),
					isSource: n.isSource, isTarget: n.isTarget,
					ministry: org.ministry, agencyId: org.id,
					agencyName: org.agencyName ?? org.name,
					yearStart: yr0 + 1, yearEnd: yr1 - 1, isFallback: true,
				});
				coveredPersons.add(n.id);
				break;
			}
		}
		return out;
	});

	// ── Lane assignment (greedy interval scheduling) ─────────────────────────────

	interface Assignment { block: Block; lane: number; }

	function assignLanes(bs: Block[]): { assignments: Assignment[]; numLanes: number } {
		const sorted = [...bs].sort((a, b) => a.yearStart - b.yearStart);
		const laneEnds: number[] = [];
		const assignments: Assignment[] = [];
		for (const b of sorted) {
			let lane = laneEnds.findIndex(end => end <= b.yearStart);
			if (lane === -1) { lane = laneEnds.length; laneEnds.push(0); }
			laneEnds[lane] = b.yearEnd;
			assignments.push({ block: b, lane });
		}
		return { assignments, numLanes: Math.max(laneEnds.length, 1) };
	}

	// ── Raw groups (no y positions — needed to compute dynamic LANE_H) ───────────

	interface RawAgency {
		agencyId: string;
		agencyName: string;
		assignments: Assignment[];
		numLanes: number;
	}
	interface RawGroup {
		ministry: string;
		color: string;
		agencies: RawAgency[];
	}

	const rawGroups = $derived.by((): RawGroup[] => {
		const mm = new Map<string, Map<string, Block[]>>();
		for (const b of blocks) {
			if (!mm.has(b.ministry)) mm.set(b.ministry, new Map());
			const am = mm.get(b.ministry)!;
			if (!am.has(b.agencyId)) am.set(b.agencyId, []);
			am.get(b.agencyId)!.push(b);
		}
		return [...mm.entries()].map(([ministry, am]) => ({
			ministry, color: getMinistryColor(ministry),
			agencies: [...am.entries()].map(([agencyId, bs]) => {
				const { assignments, numLanes } = assignLanes(bs);
				return { agencyId, agencyName: bs[0].agencyName, assignments, numLanes };
			}),
		}));
	});

	// Total lane slots across all agencies
	const totalLanes = $derived(rawGroups.reduce((s, g) => s + g.agencies.reduce((a, ag) => a + ag.numLanes, 0), 0));

	// Dynamic lane height — fills the container
	const LANE_H = $derived((() => {
		if (totalLanes === 0) return 36;
		const available = cH - AXIS_H - rawGroups.length * GRP_H;
		return Math.min(MAX_LANE_H, Math.max(MIN_LANE_H, available / totalLanes));
	})());

	// ── Groups with y positions ──────────────────────────────────────────────────

	interface AgRow {
		agencyId: string;
		agencyName: string;
		assignments: Assignment[];
		numLanes: number;
		y: number;
		rowH: number; // numLanes * LANE_H
	}
	interface MGroup {
		ministry: string;
		color: string;
		rows: AgRow[];
		y: number;
		h: number;
	}

	const groups = $derived.by((): MGroup[] => {
		let y = AXIS_H;
		return rawGroups.map(rg => {
			const gy = y;
			y += GRP_H;
			const rows: AgRow[] = rg.agencies.map(ag => {
				const rowH = ag.numLanes * LANE_H;
				const ry = y; y += rowH;
				return { agencyId: ag.agencyId, agencyName: ag.agencyName, assignments: ag.assignments, numLanes: ag.numLanes, y: ry, rowH };
			});
			const h = GRP_H + rg.agencies.reduce((s, a) => s + a.numLanes * LANE_H, 0);
			return { ministry: rg.ministry, color: rg.color, rows, y: gy, h };
		});
	});

	const svgH = $derived(Math.max(cH, groups.reduce((s, g) => s + g.h, AXIS_H) + 8));

	// ── Scales ───────────────────────────────────────────────────────────────────

	const xScale = $derived(
		d3.scaleLinear<number>().domain([yr0, yr1]).range([LABEL_W, W - PAD_R])
	);
	const ticks = $derived(d3.range(yr0, yr1 + 1) as number[]);

	// ── Tooltip ──────────────────────────────────────────────────────────────────
	let hov  = $state<Block | null>(null);
	let hx   = $state(0);
	let hy   = $state(0);

	// ── Resize ───────────────────────────────────────────────────────────────────
	onMount(() => {
		const ro = new ResizeObserver(es => {
			W  = es[0].contentRect.width  || 900;
			cH = es[0].contentRect.height || 500;
		});
		if (containerEl) {
			ro.observe(containerEl);
			W  = containerEl.getBoundingClientRect().width  || 900;
			cH = containerEl.getBoundingClientRect().height || 500;
		}
		return () => ro.disconnect();
	});
</script>

<div bind:this={containerEl} class="relative w-full h-full"
     style="background: var(--pt-bg-0); overflow: hidden;">

	{#if !blocks.length}
		<div class="flex items-center justify-center h-full">
			<div class="text-center space-y-2">
				<svg class="w-10 h-10 mx-auto" style="color: var(--pt-border);" fill="none"
				     stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round"
					      d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5" />
				</svg>
				<p class="text-sm" style="color: var(--pt-text-muted);">Enable Temporal mode and find a connection to see the timeline</p>
			</div>
		</div>

	{:else}
		<svg width={W} height={svgH}
		     style="display: block; font-family: inherit; overflow: visible;">

			<!-- ── Year axis ──────────────────────────────────────── -->
			<line x1={LABEL_W} y1={AXIS_H - 4} x2={W - PAD_R} y2={AXIS_H - 4}
			      stroke="var(--pt-border)" stroke-width="1" />

			{#each ticks as yr}
				{@const x = xScale(yr)}
				<line x1={x} y1={AXIS_H - 4} x2={x} y2={svgH}
				      stroke="var(--pt-border-muted)" stroke-width="0.75" opacity="0.4" />
				<text x={x} y={AXIS_H - 12} text-anchor="middle"
				      fill="var(--pt-text-muted)" font-size="11"
				      font-family="'Fira Mono','JetBrains Mono','Consolas',monospace">{yr}</text>
				<line x1={x} y1={AXIS_H - 9} x2={x} y2={AXIS_H - 4}
				      stroke="var(--pt-border)" stroke-width="1" />
			{/each}

			<!-- Label / timeline divider -->
			<line x1={LABEL_W} y1={0} x2={LABEL_W} y2={svgH}
			      stroke="var(--pt-border)" stroke-width="1" />

			<!-- ── Ministry groups ────────────────────────────────── -->
			{#each groups as g}
				<!-- Group background tint + left accent -->
				<rect x={0} y={g.y} width={W} height={g.h} fill="{g.color}10" />
				<rect x={0} y={g.y} width={3} height={g.h} fill={g.color} />
				<line x1={0} y1={g.y} x2={W} y2={g.y} stroke="{g.color}55" stroke-width="1" />
				<!-- Ministry label (all-caps, colored) -->
				<text x={8} y={g.y + GRP_H / 2 + 4} fill={g.color}
				      font-size="9.5" font-weight="700" letter-spacing="0.06em">
					{trunc(g.ministry, 26)}
				</text>

				{#each g.rows as row}
					{@const hier = orgHierarchy(row.agencyName, g.ministry)}
					{@const direct = hier[0] ?? row.agencyName}
					{@const subs   = hier.slice(1)}
					{@const isExp  = expandedOrgs.has(row.agencyId)}

					<!-- Row bottom border -->
					<line x1={0} y1={row.y + row.rowH} x2={W} y2={row.y + row.rowH}
					      stroke="var(--pt-border-muted)" stroke-width="0.5" opacity="0.4" />

					<!-- Label area: hierarchy label, clickable to expand -->
					<!-- svelte-ignore a11y_click_events_have_key_events -->
					<!-- svelte-ignore a11y_no_static_element_interactions -->
					<g onclick={() => subs.length > 0 && toggleOrg(row.agencyId)}
					   style={subs.length > 0 ? 'cursor: pointer;' : ''}>
						<!-- Hover hit-area for label region -->
						<rect x={0} y={row.y} width={LABEL_W - 1} height={row.rowH} fill="transparent" />

						<!-- Direct agency (line 1) -->
						<text
							x={8}
							y={row.y + (isExp && subs.length > 0 ? 14 : row.rowH / 2 + 4)}
							fill="var(--pt-text-secondary)"
							font-size="9.5"
							dominant-baseline={isExp && subs.length > 0 ? 'auto' : 'middle'}
						>
							{#if subs.length > 0}
								<!-- Toggle arrow + direct label -->
								<tspan fill={g.color} font-size="8">{isExp ? '▼ ' : '▶ '}</tspan>
								<tspan font-weight="600">{trunc(direct, 19)}</tspan>
							{:else}
								{trunc(direct, 21)}
							{/if}
						</text>

						<!-- Sub-unit lines (visible when expanded) -->
						{#if isExp}
							{#each subs as sub, si}
								<text
									x={12}
									y={row.y + 26 + si * 13}
									fill="var(--pt-text-muted)"
									font-size="8.5"
								>↳ {trunc(sub, 22)}</text>
							{/each}
						{:else if subs.length > 0}
							<!-- Collapsed hint: show first sub with ellipsis -->
							<text x={12} y={row.y + row.rowH / 2 + 14}
							      fill="var(--pt-text-muted)" font-size="8" opacity="0.7">
								↳ {trunc(subs[0], 22)}{subs.length > 1 ? ` +${subs.length - 1}` : ''}
							</text>
						{/if}
					</g>

					<!-- ── Timeline blocks per lane ────────────────── -->
					{#each row.assignments as { block: b, lane }}
						{@const bx  = xScale(b.yearStart)}
						{@const bx2 = xScale(b.yearEnd)}
						{@const bw  = Math.max(bx2 - bx, 16)}
						{@const laneY  = row.y + lane * LANE_H}
						{@const hasLabel = b.isSource || b.isTarget}
						{@const bPad = 4}
						{@const bh  = LANE_H - bPad * 2 - (hasLabel ? BADGE_H : 0)}
						{@const by  = laneY + bPad}

						{#if b.isFallback}
							<!-- Dashed outline block (no precise date) -->
							<rect x={bx} y={by} width={bw} height={bh}
							      fill={b.color} rx="2" opacity="0.2" />
							<rect x={bx} y={by} width={bw} height={bh}
							      fill="none" stroke={b.color} stroke-width="1.5"
							      stroke-dasharray="4,3" rx="2" opacity="0.65" />
							{#if bw > 18}
								<text x={bx + bw / 2} y={by + bh / 2 + 4}
								      text-anchor="middle" fill={b.color}
								      font-size={Math.min(10, LANE_H * 0.28)}
								      font-weight="700" pointer-events="none"
								      font-family="'Fira Mono','JetBrains Mono','Consolas',monospace"
								>{b.initials}</text>
							{/if}
						{:else}
							<!-- Solid block with drop shadow -->
							<rect x={bx + 1} y={by + 1} width={bw} height={bh}
							      fill="rgba(0,0,0,0.2)" rx="2" />
							<rect x={bx} y={by} width={bw} height={bh}
							      fill={b.color} rx="2" opacity="0.9"
							      style="cursor: pointer;"
							      onmouseenter={(e) => { hov = b; hx = e.clientX; hy = e.clientY; }}
							      onmouseleave={() => { hov = null; }} />
							<!-- Year span label inside block (if wide enough) -->
							{#if bw > 60}
								<text x={bx + bw / 2} y={by + bh / 2 + 4}
								      text-anchor="middle" fill="white"
								      font-size={Math.min(10, LANE_H * 0.26)}
								      font-weight="600" pointer-events="none"
								      font-family="'Fira Mono','JetBrains Mono','Consolas',monospace"
								>{b.initials}  {b.yearStart}–{b.yearEnd}</text>
							{:else if bw > 24}
								<text x={bx + bw / 2} y={by + bh / 2 + 4}
								      text-anchor="middle" fill="white"
								      font-size={Math.min(10, LANE_H * 0.28)}
								      font-weight="700" pointer-events="none"
								      font-family="'Fira Mono','JetBrains Mono','Consolas',monospace"
								>{b.initials}</text>
							{/if}
						{/if}

						<!-- SOURCE / TARGET badge below block -->
						{#if hasLabel}
							<text x={bx + bw / 2}
							      y={by + bh + BADGE_H - 1}
							      text-anchor="middle"
							      fill={b.isSource ? '#68b9e5' : '#3dcc91'}
							      font-size="7.5" font-weight="700" letter-spacing="0.07em"
							      pointer-events="none">{b.isSource ? '▲ SOURCE' : '▼ TARGET'}</text>
						{/if}
					{/each}
				{/each}
			{/each}

		</svg>
	{/if}

	<!-- Hover tooltip -->
	{#if hov && !hov.isFallback}
		<div class="fixed z-50 pointer-events-none px-2.5 py-2"
		     style="left: {hx + 12}px; top: {hy - 6}px;
		            background: var(--pt-bg-2); border: 1px solid var(--pt-border);
		            border-radius: 2px; box-shadow: 0 4px 14px rgba(0,0,0,0.45); min-width: 180px;">
			<p class="text-sm font-semibold leading-snug" style="color: var(--pt-text-primary);">{hov.personName}</p>
			<p class="text-sm mt-0.5 tabular-nums" style="color: var(--pt-text-muted);">{hov.yearStart}–{hov.yearEnd}</p>
			<p class="mt-1 leading-snug" style="color: var(--pt-text-secondary); font-size: 10px;">{hov.agencyName}</p>
			{#if hov.isSource}
				<span class="pt-label mt-1 inline-block" style="color: #68b9e5;">▲ SOURCE</span>
			{:else if hov.isTarget}
				<span class="pt-label mt-1 inline-block" style="color: #3dcc91;">▼ TARGET</span>
			{/if}
		</div>
	{/if}
</div>
