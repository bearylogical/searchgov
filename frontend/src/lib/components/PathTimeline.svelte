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
		role?: string; // most-recent rank/title from employment profile
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
	const MIN_LANE_H = 36;
	const MAX_LANE_H = 90;
	const AXIS_H     = 42;
	const PAD_R      = 16;
	const BADGE_H    = 13;
	const CURRENT_YEAR = new Date().getFullYear();

	// Match Blueprint palette from app.css
	const COLOR_SOURCE = '#137CBD'; // var(--pt-blue)
	const COLOR_TARGET = '#0D8050'; // var(--pt-green)
	const COLOR_PATH   = '#6366f1'; // indigo for intermediates

	// Collapsible org hierarchy state
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
		if (n.isSource) return COLOR_SOURCE;
		if (n.isTarget) return COLOR_TARGET;
		return COLOR_PATH;
	}

	function trunc(s: string, max: number) {
		return s.length > max ? s.slice(0, max - 1) + '…' : s;
	}

	/** Strip ministry prefix and split by " : " → hierarchy array */
	function orgHierarchy(agencyName: string, ministry: string): string[] {
		let name = agencyName ?? '';
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
		role?: string;
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
				initials: initials(person.name), role: person.role,
				color: blockColor(person),
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

	// ── Fallback blocks for source/target whose edge has no yearLabel ────────────

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
					initials: initials(n.name), role: n.role,
					color: blockColor(n),
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

	// ── Raw groups ───────────────────────────────────────────────────────────────

	interface RawAgency { agencyId: string; agencyName: string; assignments: Assignment[]; numLanes: number; }
	interface RawGroup  { ministry: string; color: string; agencies: RawAgency[]; }

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

	const totalLanes = $derived(rawGroups.reduce((s, g) => s + g.agencies.reduce((a, ag) => a + ag.numLanes, 0), 0));

	// Dynamic lane height: scale up to fill container if possible, else MIN
	const LANE_H = $derived((() => {
		if (totalLanes === 0) return MIN_LANE_H;
		const available = cH - AXIS_H - rawGroups.length * GRP_H;
		const scaled = available / totalLanes;
		return Math.min(MAX_LANE_H, Math.max(MIN_LANE_H, scaled));
	})());

	// ── Groups with y positions ──────────────────────────────────────────────────

	interface AgRow { agencyId: string; agencyName: string; assignments: Assignment[]; numLanes: number; y: number; rowH: number; }
	interface MGroup { ministry: string; color: string; rows: AgRow[]; y: number; h: number; }

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

	// Natural content height; SVG is sized to this (container scrolls if it overflows)
	const naturalH = $derived(groups.reduce((s, g) => s + g.h, AXIS_H) + 8);
	const svgH     = $derived(Math.max(naturalH, cH));

	// ── Scales ───────────────────────────────────────────────────────────────────

	const xScale = $derived(
		d3.scaleLinear<number>().domain([yr0, yr1]).range([LABEL_W, W - PAD_R])
	);
	const ticks = $derived(d3.range(yr0, yr1 + 1) as number[]);

	// ── Rendered block positions (for connectors) ────────────────────────────────

	interface RenderedBlock {
		block: Block;
		agencyId: string;
		lane: number;
		bx: number; bw: number; by: number; bh: number;
		cx: number; cy: number; // center
		rx: number; // right edge x
	}

	const renderedBlocks = $derived.by((): RenderedBlock[] => {
		const out: RenderedBlock[] = [];
		for (const g of groups) {
			for (const row of g.rows) {
				for (const { block, lane } of row.assignments) {
					const laneY  = row.y + lane * LANE_H;
					const hasLbl = block.isSource || block.isTarget;
					const bPad   = 4;
					const bh     = LANE_H - bPad * 2 - (hasLbl ? BADGE_H : 0);
					const by_    = laneY + bPad;
					const bx     = xScale(block.yearStart);
					const bw     = Math.max(xScale(block.yearEnd) - bx, 16);
					out.push({
						block, agencyId: row.agencyId, lane,
						bx, bw, by: by_, bh,
						cx: bx + bw / 2, cy: by_ + bh / 2,
						rx: bx + bw,
					});
				}
			}
		}
		return out;
	});

	// ── Path person sequence ─────────────────────────────────────────────────────

	const pathPersonOrder = $derived.by((): string[] => {
		const nm = new Map(nodes.map(n => [n.id, n]));
		const adj = new Map<string, string[]>();
		for (const e of edges) {
			if (!e.inPath) continue;
			const sid = eid(e.source), tid = eid(e.target);
			if (!adj.has(sid)) adj.set(sid, []);
			if (!adj.has(tid)) adj.set(tid, []);
			adj.get(sid)!.push(tid);
			adj.get(tid)!.push(sid);
		}
		const source = nodes.find(n => n.isSource && n.inPath);
		if (!source) return [];
		const result: string[] = [];
		const visited = new Set<string>();
		let curr = source.id;
		while (curr) {
			visited.add(curr);
			const n = nm.get(curr);
			if (n?.type === 'person') result.push(curr);
			curr = (adj.get(curr) ?? []).find(id => !visited.has(id)) ?? '';
		}
		return result;
	});

	// ── Continuity lines: same person across multiple agency rows ────────────────

	interface ConnLine { x1: number; y1: number; x2: number; y2: number; color: string; personId: string; }

	const continuityLines = $derived.by((): ConnLine[] => {
		const byPerson = new Map<string, RenderedBlock[]>();
		for (const rb of renderedBlocks) {
			if (!byPerson.has(rb.block.personId)) byPerson.set(rb.block.personId, []);
			byPerson.get(rb.block.personId)!.push(rb);
		}
		const lines: ConnLine[] = [];
		for (const [, rbs] of byPerson) {
			if (rbs.length < 2) continue;
			// Only draw between blocks in DIFFERENT agency rows
			const sorted = [...rbs].sort((a, b) => a.block.yearStart - b.block.yearStart);
			for (let i = 0; i < sorted.length - 1; i++) {
				const from = sorted[i], to = sorted[i + 1];
				if (from.agencyId === to.agencyId) continue; // same row — no line needed
				lines.push({ x1: from.rx, y1: from.cy, x2: to.bx, y2: to.cy, color: from.block.color, personId: from.block.personId });
			}
		}
		return lines;
	});

	// ── Path arrows: connection between consecutive path persons ─────────────────

	interface Arrow { x1: number; y1: number; x2: number; y2: number; sameRow: boolean; overlapX: number; p1Id: string; p2Id: string; }

	const pathArrows = $derived.by((): Arrow[] => {
		const rbByPerson = new Map<string, RenderedBlock[]>();
		for (const rb of renderedBlocks) {
			if (!rbByPerson.has(rb.block.personId)) rbByPerson.set(rb.block.personId, []);
			rbByPerson.get(rb.block.personId)!.push(rb);
		}
		const arrows: Arrow[] = [];
		for (let i = 0; i < pathPersonOrder.length - 1; i++) {
			const rbs1 = rbByPerson.get(pathPersonOrder[i]) ?? [];
			const rbs2 = rbByPerson.get(pathPersonOrder[i + 1]) ?? [];
			if (!rbs1.length || !rbs2.length) continue;

			// Prefer pair sharing the same agencyId
			let r1: RenderedBlock | undefined, r2: RenderedBlock | undefined;
			outer: for (const a of rbs1) {
				for (const b of rbs2) {
					if (a.agencyId === b.agencyId) { r1 = a; r2 = b; break outer; }
				}
			}
			if (!r1) r1 = rbs1[rbs1.length - 1];
			if (!r2) r2 = rbs2[0];

			const sameRow = r1.agencyId === r2.agencyId;
			// Overlap midpoint x
			const overlapStart = Math.max(r1.block.yearStart, r2.block.yearStart);
			const overlapEnd   = Math.min(r1.block.yearEnd,   r2.block.yearEnd);
			const overlapX     = xScale(overlapStart < overlapEnd ? (overlapStart + overlapEnd) / 2 : (r1.block.yearEnd + r2.block.yearStart) / 2);

			arrows.push({
				x1: r1.cx, y1: sameRow ? r1.by + r1.bh : r1.cy,
				x2: r2.cx, y2: sameRow ? r2.by          : r2.cy,
				sameRow, overlapX,
				p1Id: pathPersonOrder[i], p2Id: pathPersonOrder[i + 1],
			});
		}
		return arrows;
	});

	// ── Hover state ──────────────────────────────────────────────────────────────
	let hov             = $state<Block | null>(null);
	let hx              = $state(0);
	let hy              = $state(0);
	let hoveredPersonId = $state<string | null>(null);

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

<div bind:this={containerEl} class="absolute inset-0"
     style="background: var(--pt-bg-0); overflow-x: hidden; overflow-y: auto;">

	{#if !blocks.length}
		<div class="absolute inset-0 flex items-center justify-center">
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

			<defs>
				<!-- Arrowhead for path connection arrows -->
				<marker id="arr-fwd" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
					<path d="M0,0.5 L5,3 L0,5.5 Z" fill="rgba(255,255,255,0.55)" />
				</marker>
				<!-- Arrowhead for continuity line (path-colored) -->
				<marker id="arr-cont-blue"  markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
					<path d="M0,0.5 L5,3 L0,5.5 Z" fill="{COLOR_SOURCE}99" />
				</marker>
				<marker id="arr-cont-green" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
					<path d="M0,0.5 L5,3 L0,5.5 Z" fill="{COLOR_TARGET}99" />
				</marker>
				<marker id="arr-cont-indigo" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
					<path d="M0,0.5 L5,3 L0,5.5 Z" fill="{COLOR_PATH}99" />
				</marker>
			</defs>

			<!-- ── Year axis ──────────────────────────────────────── -->
			<line x1={LABEL_W} y1={AXIS_H - 4} x2={W - PAD_R} y2={AXIS_H - 4}
			      stroke="var(--pt-border)" stroke-width="1" />
			{#each ticks as yr}
				{@const x = xScale(yr)}
				<line x1={x} y1={AXIS_H - 4} x2={x} y2={svgH}
				      stroke="var(--pt-border-muted)" stroke-width="0.75" opacity="0.35" />
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
				<rect x={0} y={g.y} width={W} height={g.h} fill="{g.color}10" />
				<rect x={0} y={g.y} width={3} height={g.h} fill={g.color} />
				<line x1={0} y1={g.y} x2={W} y2={g.y} stroke="{g.color}55" stroke-width="1" />
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
					      stroke="var(--pt-border-muted)" stroke-width="0.5" opacity="0.45" />

					<!-- Lane separators within multi-lane rows -->
					{#if row.numLanes > 1}
						{#each Array(row.numLanes - 1) as _, li}
							<line x1={LABEL_W} y1={row.y + (li + 1) * LANE_H}
							      x2={W - PAD_R} y2={row.y + (li + 1) * LANE_H}
							      stroke="var(--pt-border-muted)" stroke-width="0.4" opacity="0.3"
							      stroke-dasharray="3,4" />
						{/each}
					{/if}

					<!-- Label area — clickable to expand hierarchy -->
					<!-- svelte-ignore a11y_click_events_have_key_events -->
					<!-- svelte-ignore a11y_no_static_element_interactions -->
					<g onclick={() => subs.length > 0 && toggleOrg(row.agencyId)}
					   style={subs.length > 0 ? 'cursor: pointer;' : ''}>
						<rect x={0} y={row.y} width={LABEL_W - 1} height={row.rowH} fill="transparent" />

						<!-- Direct agency name (line 1 — prominently styled) -->
						<text
							x={8}
							y={row.y + (isExp && subs.length > 0 ? 15 : row.rowH / 2 + (subs.length > 0 ? -5 : 4))}
							fill="var(--pt-text-primary)"
							font-size="10"
							font-weight="600"
						>
							{#if subs.length > 0}
								<tspan fill={g.color} font-size="8.5">{isExp ? '▼' : '▶'} </tspan>
							{/if}{trunc(direct, 20)}
						</text>

						<!-- Sub-unit hint / expanded sub-levels -->
						{#if subs.length > 0}
							{#if isExp}
								{#each subs as sub, si}
									<text x={13} y={row.y + 27 + si * 13}
									      fill="var(--pt-text-muted)" font-size="8.5">
										↳ {trunc(sub, 21)}
									</text>
								{/each}
							{:else}
								<!-- Collapsed hint -->
								<text x={12} y={row.y + row.rowH / 2 + 9}
								      fill="var(--pt-text-muted)" font-size="8.5" opacity="0.8">
									↳ {trunc(subs[0], 21)}{subs.length > 1 ? ` +${subs.length - 1}` : ''}
								</text>
							{/if}
						{/if}
					</g>

					<!-- ── Timeline blocks per lane ────────────────── -->
					{#each row.assignments as { block: b, lane }}
						{@const laneY  = row.y + lane * LANE_H}
						{@const hasLbl = b.isSource || b.isTarget}
						{@const bPad   = 4}
						{@const bh     = LANE_H - bPad * 2 - (hasLbl ? BADGE_H : 0)}
						{@const by_    = laneY + bPad}
						{@const bx     = xScale(b.yearStart)}
						{@const bw     = Math.max(xScale(b.yearEnd) - bx, 16)}

						{@const midX   = bx + bw / 2}
						{@const midY   = by_ + bh / 2}
						{@const nSize  = Math.min(11, Math.max(8.5, LANE_H * 0.26))}
						{@const rSize  = Math.max(7.5, nSize - 2)}
						{@const hasRole = !!b.role && bh > 26}

						{@const fbDimmed = hoveredPersonId !== null && hoveredPersonId !== b.personId}
						{#if b.isFallback}
							<rect x={bx} y={by_} width={bw} height={bh} fill={b.color} rx="2" opacity={fbDimmed ? 0.05 : 0.2} />
							<rect x={bx} y={by_} width={bw} height={bh}
							      fill="none" stroke={b.color} stroke-width="1.5"
							      stroke-dasharray="4,3" rx="2" opacity={fbDimmed ? 0.1 : 0.65} />
							{#if bw > 18}
								<text x={midX} y={midY + 4} text-anchor="middle"
								      fill={b.color} font-size={nSize} font-weight="700"
								      opacity={fbDimmed ? 0.1 : 1}
								      pointer-events="none">{b.initials}</text>
							{/if}
						{:else}
							{@const isHov    = hoveredPersonId === b.personId}
							{@const isDimmed = hoveredPersonId !== null && !isHov}
							<!-- Drop shadow + main block -->
							<rect x={bx + 1} y={by_ + 1} width={bw} height={bh} fill="rgba(0,0,0,0.2)" rx="2"
							      opacity={isDimmed ? 0.1 : 0.9} />
							<rect x={bx} y={by_} width={bw} height={bh}
							      fill={b.color} rx="2" opacity={isDimmed ? 0.2 : 0.9}
							      style="cursor: pointer; transition: opacity 0.15s;"
							      onmouseenter={(e) => { hov = b; hx = e.clientX; hy = e.clientY; hoveredPersonId = b.personId; }}
							      onmouseleave={() => { hov = null; hoveredPersonId = null; }} />
							<!-- Highlight ring when this block is hovered -->
							{#if isHov}
								<rect x={bx - 2} y={by_ - 2} width={bw + 4} height={bh + 4}
								      fill="none" stroke="white" stroke-width="2" rx="3"
								      opacity="0.7" pointer-events="none" />
							{/if}
							{#if hasLbl}
								<rect x={bx} y={by_} width={bw} height={3} fill="white" rx="2" opacity="0.25" pointer-events="none" />
							{/if}

							<!-- ── Block text: full name + role ───────── -->
							{#if bw > 90}
								<!-- Wide: full name on line 1, role (if any) on line 2 -->
								<text text-anchor="middle" pointer-events="none"
								      x={midX} y={hasRole ? midY - 2 : midY + 4}>
									<tspan x={midX} dy="0"
									       fill="white" font-size={nSize} font-weight="700"
									       font-family="inherit"
									>{trunc(b.personName, Math.floor(bw / (nSize * 0.62)))}</tspan>
									{#if hasRole}
										<tspan x={midX} dy={nSize + 3}
										       fill="rgba(255,255,255,0.6)" font-size={rSize}
										       font-family="inherit"
										>{trunc(b.role!, Math.floor(bw / (rSize * 0.62)))}</tspan>
									{/if}
								</text>
							{:else if bw > 44}
								<!-- Medium: first name only -->
								<text x={midX} y={midY + 4} text-anchor="middle" pointer-events="none"
								      fill="white" font-size={nSize} font-weight="700" font-family="inherit"
								>{trunc(b.personName.split(' ')[0], Math.floor(bw / (nSize * 0.62)))}</text>
							{:else if bw > 20}
								<!-- Narrow: initials -->
								<text x={midX} y={midY + 4} text-anchor="middle" pointer-events="none"
								      fill="white" font-size={nSize} font-weight="700"
								      font-family="'Fira Mono','JetBrains Mono','Consolas',monospace"
								>{b.initials}</text>
							{/if}
						{/if}

						<!-- SOURCE / TARGET badge -->
						{#if hasLbl}
							<text x={bx + bw / 2} y={by_ + bh + BADGE_H - 1}
							      text-anchor="middle"
							      fill={b.isSource ? '#68b9e5' : '#3dcc91'}
							      font-size="7.5" font-weight="700" letter-spacing="0.07em"
							      pointer-events="none">{b.isSource ? '▲ SOURCE' : '▼ TARGET'}</text>
						{/if}
					{/each}
				{/each}
			{/each}

			<!-- ── Continuity lines: same person across different agency rows ── -->
			{#each continuityLines as cl}
				{@const dx = cl.x2 - cl.x1}
				{@const clDimmed = hoveredPersonId !== null && hoveredPersonId !== cl.personId}
				<!-- Bezier: exit right side of block, arc over to left side of next block -->
				<path d="M {cl.x1} {cl.y1} C {cl.x1 + Math.max(30, dx * 0.35)} {cl.y1} {cl.x2 - Math.max(30, dx * 0.35)} {cl.y2} {cl.x2} {cl.y2}"
				      fill="none" stroke={cl.color} stroke-width={clDimmed ? 1 : 1.5}
				      stroke-dasharray="5,3" opacity={clDimmed ? 0.1 : 0.5}
				      marker-end={cl.color === COLOR_SOURCE ? 'url(#arr-cont-blue)' : cl.color === COLOR_TARGET ? 'url(#arr-cont-green)' : 'url(#arr-cont-indigo)'} />
			{/each}

			<!-- ── Path arrows: linkage between consecutive path persons ── -->
			{#each pathArrows as pa}
				{@const arrowDimmed = hoveredPersonId !== null && hoveredPersonId !== pa.p1Id && hoveredPersonId !== pa.p2Id}
				{#if pa.sameRow}
					<!-- Same agency row: vertical connecting bracket at overlap midpoint -->
					<line x1={pa.overlapX} y1={pa.y1} x2={pa.overlapX} y2={pa.y2}
					      stroke="rgba(255,255,255,0.45)" stroke-width="1.5"
					      opacity={arrowDimmed ? 0.1 : 1}
					      marker-end="url(#arr-fwd)" />
					<!-- Small horizontal ticks at each end -->
					<line x1={pa.overlapX - 6} y1={pa.y1} x2={pa.overlapX + 6} y2={pa.y1}
					      stroke="rgba(255,255,255,0.35)" stroke-width="1" opacity={arrowDimmed ? 0.1 : 1} />
					<line x1={pa.overlapX - 6} y1={pa.y2} x2={pa.overlapX + 6} y2={pa.y2}
					      stroke="rgba(255,255,255,0.35)" stroke-width="1" opacity={arrowDimmed ? 0.1 : 1} />
				{:else}
					<!-- Different rows: curved arrow -->
					<path d="M {pa.x1} {pa.y1} C {pa.x1} {(pa.y1 + pa.y2) / 2} {pa.x2} {(pa.y1 + pa.y2) / 2} {pa.x2} {pa.y2}"
					      fill="none" stroke="rgba(255,255,255,0.4)" stroke-width="1.5"
					      opacity={arrowDimmed ? 0.1 : 1}
					      marker-end="url(#arr-fwd)" />
				{/if}
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
			{#if hov.role}
				<p class="text-xs mt-0.5" style="color: var(--pt-text-muted);">{hov.role}</p>
			{/if}
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
