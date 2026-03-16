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
	let cH = $state(500); // observed container height

	// Layout constants
	const LABEL_W   = 170;
	const GRP_H     = 22;   // ministry header row height
	const MIN_ROW_H = 32;   // minimum agency row height
	const MAX_ROW_H = 72;   // maximum (prevents huge rows when few orgs)
	const AXIS_H    = 42;   // top axis band
	const PAD_R     = 16;
	const BADGE_H   = 12;   // source/target label height below block
	const CURRENT_YEAR = new Date().getFullYear();

	// ── Helpers ────────────────────────────────────────────────────────────────

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

	// ── Data: primary blocks (edges with yearLabel) ────────────────────────────

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
		isFallback: boolean; // true = no exact date, shown with dashed outline
	}

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

	// Year extent from primary blocks
	const yr0 = $derived(
		primaryBlocks.length ? Math.min(...primaryBlocks.map(b => b.yearStart)) - 1 : 2015
	);
	const yr1 = $derived(
		primaryBlocks.length ? Math.max(...primaryBlocks.map(b => b.yearEnd))   + 1 : CURRENT_YEAR
	);

	// ── Data: add fallback blocks for source/target without yearLabel ──────────
	const blocks = $derived.by((): Block[] => {
		const nm = new Map(nodes.map(n => [n.id, n]));
		const out = [...primaryBlocks];
		const coveredPersons = new Set(out.map(b => b.personId));

		for (const n of nodes) {
			if (!n.inPath || (!n.isSource && !n.isTarget)) continue;
			if (coveredPersons.has(n.id)) continue;

			// Find first adjacent inPath org edge
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

	// ── Layout: ministry → agency grouping (without y positions) ──────────────

	interface RawAgency { agencyId: string; agencyName: string; blocks: Block[]; }
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
			agencies: [...am.entries()].map(([agencyId, bs]) => ({
				agencyId, agencyName: bs[0].agencyName,
				blocks: [...bs].sort((a, b) => a.yearStart - b.yearStart),
			})),
		}));
	});

	// ── Dynamic row height to fill container ──────────────────────────────────

	const totalRows = $derived(rawGroups.reduce((s, g) => s + g.agencies.length, 0));

	const ROW_H = $derived((() => {
		if (totalRows === 0) return 36;
		const available = cH - AXIS_H - rawGroups.length * GRP_H;
		const h = Math.max(MIN_ROW_H, available / totalRows);
		return Math.min(h, MAX_ROW_H);
	})());

	// ── Layout with y positions ────────────────────────────────────────────────

	interface AgRow { agencyId: string; agencyName: string; blocks: Block[]; y: number; }
	interface MGroup { ministry: string; color: string; rows: AgRow[]; y: number; h: number; }

	const groups = $derived.by((): MGroup[] => {
		let y = AXIS_H;
		return rawGroups.map(rg => {
			const gy = y;
			y += GRP_H;
			const rows: AgRow[] = rg.agencies.map(ag => {
				const ry = y; y += ROW_H;
				return { agencyId: ag.agencyId, agencyName: ag.agencyName, blocks: ag.blocks, y: ry };
			});
			const h = GRP_H + rg.agencies.length * ROW_H;
			return { ministry: rg.ministry, color: rg.color, rows, y: gy, h };
		});
	});

	// SVG height = container height so it fills exactly
	const svgH = $derived(Math.max(cH, groups.reduce((s, g) => s + g.h, AXIS_H) + 8));

	// ── Scales ────────────────────────────────────────────────────────────────

	const xScale = $derived(
		d3.scaleLinear<number>().domain([yr0, yr1]).range([LABEL_W, W - PAD_R])
	);
	const ticks = $derived(d3.range(yr0, yr1 + 1) as number[]);

	// ── Tooltip ───────────────────────────────────────────────────────────────
	let hov  = $state<Block | null>(null);
	let hx   = $state(0);
	let hy   = $state(0);

	// ── Resize ────────────────────────────────────────────────────────────────
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

	// Truncate labels
	function trunc(s: string, max: number) {
		return s.length > max ? s.slice(0, max - 1) + '…' : s;
	}
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

			<!-- ── Year axis ─────────────────────────────────── -->
			<!-- Axis baseline -->
			<line x1={LABEL_W} y1={AXIS_H - 4} x2={W - PAD_R} y2={AXIS_H - 4}
			      stroke="var(--pt-border)" stroke-width="1" />

			{#each ticks as yr}
				{@const x = xScale(yr)}
				<!-- Gridline -->
				<line x1={x} y1={AXIS_H - 4} x2={x} y2={svgH}
				      stroke="var(--pt-border-muted)" stroke-width="0.75" opacity="0.45" />
				<!-- Year label -->
				<text x={x} y={AXIS_H - 12} text-anchor="middle"
				      fill="var(--pt-text-muted)" font-size="11"
				      font-family="'Fira Mono','JetBrains Mono','Consolas',monospace">{yr}</text>
				<!-- Tick -->
				<line x1={x} y1={AXIS_H - 9} x2={x} y2={AXIS_H - 4}
				      stroke="var(--pt-border)" stroke-width="1" />
			{/each}

			<!-- Label / timeline separator -->
			<line x1={LABEL_W} y1={0} x2={LABEL_W} y2={svgH}
			      stroke="var(--pt-border)" stroke-width="1" />

			<!-- ── Ministry groups ──────────────────────────── -->
			{#each groups as g}
				<!-- Group background tint -->
				<rect x={0} y={g.y} width={W} height={g.h} fill="{g.color}10" />
				<!-- Left accent bar -->
				<rect x={0} y={g.y} width={3} height={g.h} fill={g.color} />
				<!-- Group top border -->
				<line x1={0} y1={g.y} x2={W} y2={g.y} stroke="{g.color}55" stroke-width="1" />
				<!-- Ministry label -->
				<text x={8} y={g.y + GRP_H / 2 + 4} fill={g.color}
				      font-size="10" font-weight="700" letter-spacing="0.06em">
					{trunc(g.ministry, 26)}
				</text>

				{#each g.rows as row}
					<!-- Row bottom separator -->
					<line x1={LABEL_W} y1={row.y + ROW_H} x2={W} y2={row.y + ROW_H}
					      stroke="var(--pt-border-muted)" stroke-width="0.5" opacity="0.45" />
					<!-- Agency label -->
					<text x={8} y={row.y + ROW_H / 2 + 4} fill="var(--pt-text-secondary)" font-size="9.5">
						{trunc(row.agencyName, 24)}
					</text>

					<!-- Tenure blocks -->
					{#each row.blocks as b}
						{@const bx  = xScale(b.yearStart)}
						{@const bx2 = xScale(b.yearEnd)}
						{@const bw  = Math.max(bx2 - bx, 16)}
						{@const by  = row.y + Math.max(4, ROW_H * 0.12)}
						{@const bh  = ROW_H - Math.max(8, ROW_H * 0.24) - (b.isSource || b.isTarget ? BADGE_H : 0)}

						{#if b.isFallback}
							<!-- Fallback: dashed outline, translucent fill -->
							<rect x={bx} y={by} width={bw} height={bh}
							      fill={b.color} rx="2" opacity="0.25" />
							<rect x={bx} y={by} width={bw} height={bh}
							      fill="none" stroke={b.color} stroke-width="1.5"
							      stroke-dasharray="4,3" rx="2" opacity="0.7" />
						{:else}
							<!-- Normal block with subtle shadow -->
							<rect x={bx + 1} y={by + 1} width={bw} height={bh}
							      fill="rgba(0,0,0,0.2)" rx="2" />
							<rect x={bx} y={by} width={bw} height={bh}
							      fill={b.color} rx="2" opacity="0.9"
							      style="cursor: pointer;"
							      onmouseenter={(e) => { hov = b; hx = e.clientX; hy = e.clientY; }}
							      onmouseleave={() => { hov = null; }} />
							{#if b.isSource || b.isTarget}
								<!-- White accent stripe at top -->
								<rect x={bx} y={by} width={bw} height={3}
								      fill="white" rx="2" opacity="0.3" pointer-events="none" />
							{/if}
						{/if}

						<!-- Initials label -->
						{#if bw > 18}
							<text x={bx + bw / 2} y={by + bh / 2 + 4}
							      text-anchor="middle" fill="white"
							      font-size={Math.min(11, ROW_H * 0.28)}
							      font-weight="700" pointer-events="none"
							      font-family="'Fira Mono','JetBrains Mono','Consolas',monospace"
							>{b.initials}</text>
						{/if}

						<!-- Source / Target badge always visible below block -->
						{#if b.isSource || b.isTarget}
							<text x={bx + bw / 2} y={by + bh + BADGE_H - 1}
							      text-anchor="middle"
							      fill={b.isSource ? '#68b9e5' : '#3dcc91'}
							      font-size="8" font-weight="700" letter-spacing="0.06em"
							      pointer-events="none"
							>{b.isSource ? '▲ SOURCE' : '▼ TARGET'}</text>
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
		            border-radius: 2px; box-shadow: 0 4px 14px rgba(0,0,0,0.45); min-width: 148px;">
			<p class="text-sm font-semibold leading-snug" style="color: var(--pt-text-primary);">{hov.personName}</p>
			<p class="text-sm mt-0.5" style="color: var(--pt-text-muted); font-variant-numeric: tabular-nums;">{hov.yearStart}–{hov.yearEnd}</p>
			<p class="text-sm mt-0.5 truncate" style="color: var(--pt-text-secondary);">{hov.agencyName}</p>
			{#if hov.isSource}
				<span class="pt-label mt-1 inline-block" style="color: #68b9e5;">▲ SOURCE</span>
			{:else if hov.isTarget}
				<span class="pt-label mt-1 inline-block" style="color: #3dcc91;">▼ TARGET</span>
			{/if}
		</div>
	{/if}
</div>
