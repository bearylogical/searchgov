<script lang="ts">
	import { onMount } from 'svelte';
	import * as d3 from 'd3';

	// Minimal compatible interfaces (subset of GNode/GEdge from connectivity page)
	interface TLNode {
		id: string;
		type: 'person' | 'org';
		name: string;
		ministry?: string;
		agencyName?: string;
		isMinistry?: boolean;
		isSource: boolean;
		isTarget: boolean;
		inPath: boolean;
		person_id?: number;
		org_id?: number;
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
	let W = $state(900);

	// Layout constants
	const LABEL_W = 160;
	const ROW_H   = 34;
	const GRP_H   = 22;   // ministry header height
	const AXIS_H  = 40;   // year-axis band at top
	const PAD_R   = 20;
	const CURRENT_YEAR = new Date().getFullYear();

	// ── Helpers ────────────────────────────────────────────────────────────────

	function parseYears(label: string): [number, number] | null {
		// Handles "2021–2023", "2021-2023", "2023–now", "2021"
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

	// ── Data derivation ────────────────────────────────────────────────────────

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
	}

	const blocks = $derived.by((): Block[] => {
		const nm = new Map(nodes.map(n => [n.id, n]));
		const seen = new Set<string>();
		const out: Block[] = [];
		for (const e of edges) {
			if (!e.yearLabel) continue;
			const yr = parseYears(e.yearLabel);
			if (!yr) continue;
			const sid = typeof e.source === 'string' ? e.source : (e.source as TLNode).id;
			const tid = typeof e.target === 'string' ? e.target : (e.target as TLNode).id;
			const sn = nm.get(sid), tn = nm.get(tid);
			if (!sn || !tn) continue;
			const person = sn.type === 'person' ? sn : tn;
			const org    = sn.type === 'org'    ? sn : tn;
			if (person.type !== 'person' || org.type !== 'org' || !org.ministry) continue;
			const key = `${person.id}::${org.id}`;
			if (seen.has(key)) continue;
			seen.add(key);
			out.push({
				personId:   person.id,
				personName: person.name,
				initials:   initials(person.name),
				color:      blockColor(person),
				isSource:   person.isSource,
				isTarget:   person.isTarget,
				ministry:   org.ministry,
				agencyId:   org.id,
				agencyName: org.agencyName ?? org.name,
				yearStart:  yr[0],
				yearEnd:    yr[1],
			});
		}
		return out;
	});

	// Ministry → agency → blocks
	interface AgRow { agencyId: string; agencyName: string; blocks: Block[]; y: number; }
	interface MGroup { ministry: string; color: string; rows: AgRow[]; y: number; h: number; }

	const groups = $derived.by((): MGroup[] => {
		const mm = new Map<string, Map<string, Block[]>>();
		for (const b of blocks) {
			if (!mm.has(b.ministry)) mm.set(b.ministry, new Map());
			const am = mm.get(b.ministry)!;
			if (!am.has(b.agencyId)) am.set(b.agencyId, []);
			am.get(b.agencyId)!.push(b);
		}
		let y = AXIS_H;
		return [...mm.entries()].map(([ministry, am]) => {
			const gy = y;
			y += GRP_H;
			const rows: AgRow[] = [...am.entries()].map(([agencyId, bs]) => {
				const ry = y; y += ROW_H;
				return {
					agencyId,
					agencyName: bs[0].agencyName,
					blocks: [...bs].sort((a, b) => a.yearStart - b.yearStart),
					y: ry,
				};
			});
			const h = GRP_H + rows.length * ROW_H;
			return { ministry, color: getMinistryColor(ministry), rows, y: gy, h };
		});
	});

	const svgH = $derived(groups.reduce((s, g) => s + g.h, AXIS_H) + 16);

	const yr0 = $derived(
		blocks.length ? Math.min(...blocks.map(b => b.yearStart)) - 1 : 2015
	);
	const yr1 = $derived(
		blocks.length ? Math.max(...blocks.map(b => b.yearEnd))   + 1 : CURRENT_YEAR
	);

	const xScale = $derived(
		d3.scaleLinear<number>().domain([yr0, yr1]).range([LABEL_W, W - PAD_R])
	);
	const ticks = $derived(d3.range(yr0, yr1 + 1) as number[]);

	// ── Tooltip ────────────────────────────────────────────────────────────────
	let hov = $state<Block | null>(null);
	let hx  = $state(0);
	let hy  = $state(0);

	// ── Resize ─────────────────────────────────────────────────────────────────
	onMount(() => {
		const ro = new ResizeObserver(es => { W = es[0].contentRect.width || 900; });
		if (containerEl) { ro.observe(containerEl); W = containerEl.getBoundingClientRect().width || 900; }
		return () => ro.disconnect();
	});
</script>

<div bind:this={containerEl} class="relative w-full h-full overflow-y-auto"
     style="background: var(--pt-bg-0);">

	{#if !blocks.length}
		<div class="flex items-center justify-center h-full">
			<div class="text-center space-y-2">
				<svg class="w-10 h-10 mx-auto" style="color: var(--pt-border);" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5" />
				</svg>
				<p class="text-sm" style="color: var(--pt-text-muted);">Enable Temporal mode and find a connection to see the timeline</p>
			</div>
		</div>

	{:else}
		<svg width={W} height={svgH} style="display: block; font-family: inherit; overflow: visible;">

			<!-- ── Year axis gridlines ──────────────────────── -->
			{#each ticks as yr}
				{@const x = xScale(yr)}
				<!-- Gridline -->
				<line x1={x} y1={AXIS_H - 4} x2={x} y2={svgH - 8}
				      stroke="var(--pt-border-muted)" stroke-width="0.75" opacity="0.5" />
				<!-- Year label -->
				<text x={x} y={AXIS_H - 14} text-anchor="middle"
				      fill="var(--pt-text-muted)" font-size="11"
				      font-family="'Fira Mono', 'JetBrains Mono', 'Consolas', monospace">{yr}</text>
				<!-- Tick mark -->
				<line x1={x} y1={AXIS_H - 10} x2={x} y2={AXIS_H - 4}
				      stroke="var(--pt-border)" stroke-width="1" />
			{/each}

			<!-- Axis baseline -->
			<line x1={LABEL_W} y1={AXIS_H - 4} x2={W - PAD_R} y2={AXIS_H - 4}
			      stroke="var(--pt-border)" stroke-width="1" />

			<!-- Label / timeline separator -->
			<line x1={LABEL_W} y1={0} x2={LABEL_W} y2={svgH}
			      stroke="var(--pt-border)" stroke-width="1" />

			<!-- ── Ministry groups ───────────────────────────── -->
			{#each groups as g}
				<!-- Group background tint -->
				<rect x={0} y={g.y} width={W} height={g.h} fill="{g.color}10" />
				<!-- Left accent bar -->
				<rect x={0} y={g.y} width={3} height={g.h} fill={g.color} />
				<!-- Group top border -->
				<line x1={0} y1={g.y} x2={W} y2={g.y}
				      stroke="{g.color}50" stroke-width="1" />
				<!-- Ministry label -->
				<text x={8} y={g.y + GRP_H / 2 + 4} fill={g.color}
				      font-size="10" font-weight="700" letter-spacing="0.06em">
					{g.ministry.length > 27 ? g.ministry.slice(0, 26) + '…' : g.ministry}
				</text>

				{#each g.rows as row}
					<!-- Row separator -->
					<line x1={LABEL_W} y1={row.y + ROW_H} x2={W} y2={row.y + ROW_H}
					      stroke="var(--pt-border-muted)" stroke-width="0.5" opacity="0.5" />
					<!-- Agency label -->
					<text x={8} y={row.y + ROW_H / 2 + 4} fill="var(--pt-text-secondary)" font-size="9.5">
						{row.agencyName.length > 25 ? row.agencyName.slice(0, 24) + '…' : row.agencyName}
					</text>

					<!-- Tenure blocks -->
					{#each row.blocks as b}
						{@const bx = xScale(b.yearStart)}
						{@const bw = Math.max(xScale(b.yearEnd) - xScale(b.yearStart), 16)}
						<!-- Shadow rect for depth -->
						<rect x={bx + 1} y={row.y + 7} width={bw} height={ROW_H - 12}
						      fill="rgba(0,0,0,0.25)" rx="2" />
						<!-- Main block -->
						<rect
							x={bx} y={row.y + 5} width={bw} height={ROW_H - 10}
							fill={b.color} rx="2" opacity="0.9"
							style="cursor: pointer;"
							onmouseenter={(e) => { hov = b; hx = e.clientX; hy = e.clientY; }}
							onmouseleave={() => { hov = null; }}
						/>
						{#if b.isSource || b.isTarget}
							<!-- Accent top stripe for source/target -->
							<rect x={bx} y={row.y + 5} width={bw} height={3}
							      fill="white" rx="2" opacity="0.35" pointer-events="none" />
						{/if}
						{#if bw > 18}
							<text
								x={bx + bw / 2} y={row.y + ROW_H / 2 + 4}
								text-anchor="middle" fill="white"
								font-size="9.5" font-weight="700"
								pointer-events="none"
								font-family="'Fira Mono', 'JetBrains Mono', 'Consolas', monospace"
							>{b.initials}</text>
						{/if}
					{/each}
				{/each}
			{/each}

		</svg>
	{/if}

	<!-- Hover tooltip (fixed so it escapes overflow:hidden) -->
	{#if hov}
		<div class="fixed z-50 pointer-events-none px-2.5 py-2"
		     style="left: {hx + 12}px; top: {hy - 6}px;
		            background: var(--pt-bg-2); border: 1px solid var(--pt-border);
		            border-radius: 2px; box-shadow: 0 4px 14px rgba(0,0,0,0.45); min-width: 140px;">
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
