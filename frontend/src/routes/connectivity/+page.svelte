<script lang="ts">
	import { onMount } from 'svelte';
	import * as d3 from 'd3';
	import { people, graph, organisations } from '$lib/api';
	import type {
		PersonResult,
		NameVariant,
		EmploymentEntry,
		PathNode,
		ColleagueNetwork,
		OrgResult
	} from '$lib/api';
	import { isAuthenticated, authReady } from '$lib/auth';
	import { goto } from '$app/navigation';
	import PersonSearch from '$lib/components/PersonSearch.svelte';
	import NameVariantZones from '$lib/components/NameVariantZones.svelte';
	import ConfidenceSlider from '$lib/components/ConfidenceSlider.svelte';
	import InfoTip from '$lib/components/InfoTip.svelte';

	$effect(() => {
		if ($authReady && !$isAuthenticated) goto('/login?redirect=/connectivity');
	});

	// ---------------------------------------------------------------------------
	// Ministry colour palette — stable assignment as ministries are discovered
	// ---------------------------------------------------------------------------
	const PALETTE = [
		'#4f46e5', '#0891b2', '#059669', '#d97706', '#dc2626',
		'#7c3aed', '#0e7490', '#15803d', '#b45309', '#be185d',
		'#6366f1', '#0284c7', '#16a34a', '#ca8a04', '#e11d48'
	];
	const ministryColorMap = new Map<string, string>();
	let nextPaletteIdx = 0;

	function getMinistryColor(ministry: string): string {
		if (!ministryColorMap.has(ministry)) {
			ministryColorMap.set(ministry, PALETTE[nextPaletteIdx % PALETTE.length]);
			nextPaletteIdx++;
		}
		return ministryColorMap.get(ministry)!;
	}

	// org_id → resolved root OrgResult
	const rootOrgCache = new Map<number, OrgResult>();

	async function fetchRootMinistry(orgId: number): Promise<OrgResult | null> {
		if (rootOrgCache.has(orgId)) return rootOrgCache.get(orgId)!;
		try {
			const root = await organisations.root(orgId);
			rootOrgCache.set(orgId, root);
			return root;
		} catch { return null; }
	}

	// D3 node positions persisted across re-renders (so ministry update doesn't
	// reset the simulation layout)
	const nodePositions = new Map<string, { x: number; y: number }>();

	// ---------------------------------------------------------------------------
	// Person slot — one for source, one for target
	// ---------------------------------------------------------------------------
	interface PersonSlot {
		selected: PersonResult | null;
		nameVariants: NameVariant[];
		career: EmploymentEntry[];
		activeNames: Set<string>;
		loading: boolean;
		error: string;
	}

	function makeSlot(): PersonSlot {
		return { selected: null, nameVariants: [], career: [], activeNames: new Set(), loading: false, error: '' };
	}

	let source = $state<PersonSlot>(makeSlot());
	let target = $state<PersonSlot>(makeSlot());
	let confidenceThreshold = $state(95);

	function activeIds(slot: PersonSlot): number[] {
		const ids = new Set<number>();
		if (slot.selected?.id) ids.add(slot.selected.id);
		for (const entry of slot.career) {
			if (entry.person_id && (!entry.person_name || slot.activeNames.has(entry.person_name))) {
				ids.add(entry.person_id);
			}
		}
		return [...ids];
	}

	const BROAD_THRESHOLD = 0.5;

	async function selectPerson(slot: PersonSlot, person: PersonResult) {
		slot.selected = person; slot.nameVariants = []; slot.career = [];
		slot.activeNames = new Set(); slot.error = ''; slot.loading = true;
		try {
			const [variants, raw] = await Promise.all([
				people.similarNames(person.name, 15, BROAD_THRESHOLD),
				people.careerByName(person.name, true, BROAD_THRESHOLD)
			]);
			slot.nameVariants = variants;
			slot.career = [...raw].sort((a, b) => {
				if (!a.start_date) return 1; if (!b.start_date) return -1;
				return a.start_date.localeCompare(b.start_date);
			});
			slot.activeNames = new Set(
				variants.filter(v => v.score >= confidenceThreshold).map(v => v.name)
			);
		} finally { slot.loading = false; }
		if (source.selected && target.selected) findPath();
	}

	function toggleVariant(slot: PersonSlot, name: string) {
		const next = new Set(slot.activeNames);
		if (next.has(name)) next.delete(name); else next.add(name);
		slot.activeNames = next;
	}

	function clearSlot(slot: PersonSlot) {
		Object.assign(slot, makeSlot());
		pathResult = null; pathError = ''; graphNodes = []; graphEdges = [];
		ministryColorMap.clear(); nextPaletteIdx = 0; nodePositions.clear();
	}

	// ---------------------------------------------------------------------------
	// D3 Graph state
	// ---------------------------------------------------------------------------
	interface GNode extends d3.SimulationNodeDatum {
		id: string;
		type: 'person' | 'org';
		name: string;
		/** Root ministry name (resolved async) */
		ministry?: string;
		person_id?: number;
		org_id?: number;
		inPath: boolean;
		isSource: boolean;
		isTarget: boolean;
		expanded: boolean;
	}

	interface GEdge extends d3.SimulationLinkDatum<GNode> {
		source: string | GNode;
		target: string | GNode;
		inPath: boolean;
	}

	let graphNodes  = $state<GNode[]>([]);
	let graphEdges  = $state<GEdge[]>([]);
	let pathResult  = $state<{ nodes: PathNode[]; length: number } | null>(null);
	let pathError   = $state('');
	let pathLoading = $state(false);
	let temporal    = $state(true);

	// Hover tooltip
	let hoveredNode = $state<GNode | null>(null);
	let hoverClientX = $state(0);
	let hoverClientY = $state(0);

	// ---------------------------------------------------------------------------
	// Path finding
	// ---------------------------------------------------------------------------
	async function findPath() {
		if (!source.selected || !target.selected) return;
		pathLoading = true; pathError = '';
		try {
			pathResult = await graph.path(activeIds(source), activeIds(target), temporal);
			buildGraphFromPath(pathResult.nodes);
			resolveMinistries();
		} catch (err: unknown) {
			pathError = err instanceof Error ? err.message : 'Failed to find path';
			pathResult = null; graphNodes = []; graphEdges = [];
		} finally { pathLoading = false; }
	}

	function buildGraphFromPath(nodes: PathNode[]) {
		const sourceId = source.selected?.id;
		const targetId = target.selected?.id;
		graphNodes = nodes.map(n => ({
			id: n.node_id,
			type: n.node_type === 'person' ? 'person' : 'org',
			name: n.name,
			person_id: n.person_id,
			org_id: n.org_id,
			inPath: true,
			isSource: n.person_id === sourceId,
			isTarget: n.person_id === targetId,
			expanded: false
		} satisfies GNode));
		graphEdges = nodes.slice(0, -1).map((n, i) => ({
			source: n.node_id,
			target: nodes[i + 1].node_id,
			inPath: true
		}));
	}

	/** Async: resolve root ministry for all org nodes, patch graphNodes to trigger re-render */
	async function resolveMinistries() {
		const orgNodes = graphNodes.filter(n => n.type === 'org' && n.org_id != null);
		if (!orgNodes.length) return;

		const resolved = await Promise.all(
			orgNodes.map(async n => {
				const root = await fetchRootMinistry(n.org_id!);
				return { id: n.id, ministry: root?.name ?? n.name };
			})
		);

		// Pre-assign palette colours so the order is deterministic
		for (const r of resolved) getMinistryColor(r.ministry);

		const patchMap = new Map(resolved.map(r => [r.id, r.ministry]));

		graphNodes = graphNodes.map(n => {
			if (patchMap.has(n.id)) return { ...n, ministry: patchMap.get(n.id) };
			// Propagate ministry to adjacent person nodes
			if (n.type === 'person') {
				for (const e of graphEdges) {
					const s = typeof e.source === 'string' ? e.source : (e.source as GNode).id;
					const t = typeof e.target === 'string' ? e.target : (e.target as GNode).id;
					if (s === n.id && patchMap.has(t)) return { ...n, ministry: patchMap.get(t) };
					if (t === n.id && patchMap.has(s)) return { ...n, ministry: patchMap.get(s) };
				}
			}
			return n;
		});
	}

	// ---------------------------------------------------------------------------
	// Node expansion
	// ---------------------------------------------------------------------------
	const networkCache = new Map<number, ColleagueNetwork>();

	async function fetchPersonNetwork(personId: number): Promise<ColleagueNetwork> {
		if (!networkCache.has(personId)) {
			networkCache.set(personId, await graph.personNetwork(personId, 1));
		}
		return networkCache.get(personId)!;
	}

	async function expandNode(node: GNode) {
		if (!node.person_id) return;
		const net  = await fetchPersonNetwork(node.person_id);
		const deg1 = net.colleagues_by_degree['1'] ?? [];
		const existingIds = new Set(graphNodes.map(n => n.id));
		const toAddNodes: GNode[] = [];
		const toAddEdges: GEdge[] = [];
		const anchorX = nodePositions.get(node.id)?.x ?? 0;
		const anchorY = nodePositions.get(node.id)?.y ?? 0;

		for (const colleague of deg1) {
			const pId = `person_${colleague.id}`;
			if (!existingIds.has(pId)) {
				toAddNodes.push({
					id: pId, type: 'person', name: colleague.name,
					person_id: colleague.id, inPath: false,
					isSource: false, isTarget: false, expanded: false,
					x: anchorX + (Math.random() - 0.5) * 80,
					y: anchorY + (Math.random() - 0.5) * 80
				});
				existingIds.add(pId);
			}
			for (const orgId of colleague.shared_organizations) {
				const oId = `org_${orgId}`;
				if (!existingIds.has(oId)) {
					toAddNodes.push({
						id: oId, type: 'org', name: `Org ${orgId}`,
						org_id: orgId, inPath: false,
						isSource: false, isTarget: false, expanded: false,
						x: anchorX + (Math.random() - 0.5) * 100,
						y: anchorY + (Math.random() - 0.5) * 100
					});
					existingIds.add(oId);
				}
				const edgeExists = (a: string, b: string) =>
					graphEdges.some(e => {
						const s = typeof e.source === 'string' ? e.source : (e.source as GNode).id;
						const t = typeof e.target === 'string' ? e.target : (e.target as GNode).id;
						return (s === a && t === b) || (s === b && t === a);
					});
				if (!edgeExists(node.id, oId)) toAddEdges.push({ source: node.id, target: oId, inPath: false });
				if (!edgeExists(pId, oId))     toAddEdges.push({ source: pId,     target: oId, inPath: false });
			}
		}

		graphNodes = [...graphNodes.map(n => n.id === node.id ? { ...n, expanded: true } : n), ...toAddNodes];
		graphEdges = [...graphEdges, ...toAddEdges];
		resolveMinistries();
	}

	// ---------------------------------------------------------------------------
	// D3 Simulation
	// ---------------------------------------------------------------------------
	let svgEl: SVGSVGElement | undefined = $state();
	let svgWidth  = $state(800);
	let svgHeight = $state(600);
	let simulation: d3.Simulation<GNode, GEdge> | undefined;

	onMount(() => {
		const ro = new ResizeObserver(entries => {
			for (const e of entries) { svgWidth = e.contentRect.width; svgHeight = e.contentRect.height; }
		});
		if (svgEl?.parentElement) ro.observe(svgEl.parentElement);
		return () => ro.disconnect();
	});

	$effect(() => {
		if (!svgEl || graphNodes.length === 0) return;
		renderD3();
	});

	function nodeRadius(d: GNode): number {
		if (d.isSource || d.isTarget) return 26;
		return d.inPath && d.type === 'person' ? 20 : 15;
	}

	function truncate(s: string, max: number): string {
		return s.length > max ? s.slice(0, max - 1) + '…' : s;
	}

	function personFill(d: GNode): string {
		if (d.isSource) return '#2563eb';
		if (d.isTarget) return '#059669';
		return d.inPath ? '#6366f1' : '#94a3b8';
	}

	function renderD3() {
		if (!svgEl) return;
		const svg = d3.select(svgEl);
		svg.selectAll('*').remove();

		// Defs
		const defs = svg.append('defs');
		const shadow = defs.append('filter').attr('id', 'node-shadow').attr('x', '-20%').attr('y', '-20%').attr('width', '140%').attr('height', '140%');
		shadow.append('feDropShadow').attr('dx', 0).attr('dy', 1).attr('stdDeviation', 2).attr('flood-opacity', 0.18);

		const g = svg.append('g');

		svg.call(
			d3.zoom<SVGSVGElement, unknown>()
				.scaleExtent([0.15, 5])
				.on('zoom', e => g.attr('transform', e.transform))
		);

		// Use stored positions for existing nodes (prevents layout reset on ministry update)
		const simNodes: GNode[] = graphNodes.map(n => ({
			...n,
			x: nodePositions.get(n.id)?.x,
			y: nodePositions.get(n.id)?.y
		}));
		const simEdges: GEdge[] = graphEdges.map(e => ({
			source: typeof e.source === 'string' ? e.source : (e.source as GNode).id,
			target: typeof e.target === 'string' ? e.target : (e.target as GNode).id,
			inPath: e.inPath
		}));

		// Lower alpha for re-renders with existing positions (ministry update)
		const hasExistingPositions = simNodes.some(n => n.x != null);

		simulation = d3.forceSimulation<GNode>(simNodes)
			.alpha(hasExistingPositions ? 0.15 : 1)
			.force('link', d3.forceLink<GNode, GEdge>(simEdges).id(d => d.id).distance(d => d.inPath ? 150 : 100))
			.force('charge', d3.forceManyBody().strength(-420))
			.force('center', d3.forceCenter(svgWidth / 2, svgHeight / 2))
			.force('collide', d3.forceCollide<GNode>(d => nodeRadius(d) + 12));

		// ── Edges ──────────────────────────────────────────
		const link = g.append('g')
			.selectAll<SVGLineElement, GEdge>('line')
			.data(simEdges)
			.join('line')
			.attr('stroke', d => d.inPath ? '#818cf8' : '#cbd5e1')
			.attr('stroke-width', d => d.inPath ? 2.5 : 1.2)
			.attr('stroke-dasharray', d => d.inPath ? null : '5,4')
			.attr('opacity', d => d.inPath ? 1 : 0.45);

		// ── Nodes ──────────────────────────────────────────
		const drag = d3.drag<SVGGElement, GNode>()
			.on('start', (event, d) => { if (!event.active) simulation?.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
			.on('drag',  (event, d) => { d.fx = event.x; d.fy = event.y; })
			.on('end',   (event, d) => { if (!event.active) simulation?.alphaTarget(0); d.fx = null; d.fy = null; });

		const node = g.append('g')
			.selectAll<SVGGElement, GNode>('g')
			.data(simNodes)
			.join('g')
			.style('cursor', d => d.type === 'person' ? 'pointer' : 'grab')
			.call(drag)
			.on('click', (_e, d) => { if (d.type === 'person') openModal(d); })
			.on('mouseover', (event, d) => {
				hoveredNode = { ...d };
				hoverClientX = event.clientX;
				hoverClientY = event.clientY;
			})
			.on('mousemove', (event) => {
				hoverClientX = event.clientX;
				hoverClientY = event.clientY;
			})
			.on('mouseout', () => { hoveredNode = null; });

		// ── Person circles ─────────────────────────────────
		const personNodes = node.filter(d => d.type === 'person');

		// Outer accent ring (source/target)
		personNodes.filter(d => d.isSource || d.isTarget)
			.append('circle')
			.attr('r', d => nodeRadius(d) + 6)
			.attr('fill', 'none')
			.attr('stroke', d => d.isSource ? '#2563eb' : '#059669')
			.attr('stroke-width', 2.5)
			.attr('stroke-dasharray', d => d.isSource ? null : '6,3')
			.attr('opacity', 0.5);

		// Main circle
		personNodes.append('circle')
			.attr('r', nodeRadius)
			.attr('fill', personFill)
			.attr('stroke', d => d.expanded ? '#fbbf24' : 'white')
			.attr('stroke-width', d => d.expanded ? 3 : 2)
			.attr('filter', 'url(#node-shadow)');

		// Initials
		personNodes.append('text')
			.attr('text-anchor', 'middle').attr('dominant-baseline', 'central')
			.attr('fill', 'white').attr('font-size', '13px').attr('font-weight', '700')
			.attr('letter-spacing', '0.5px').attr('pointer-events', 'none')
			.text(d => d.name.slice(0, 2).toUpperCase());

		// ── Org rectangles ─────────────────────────────────
		const orgNodes = node.filter(d => d.type === 'org');

		orgNodes.append('rect')
			.attr('x', -36).attr('y', -15).attr('width', 72).attr('height', 30).attr('rx', 8)
			.attr('fill', d => d.ministry ? getMinistryColor(d.ministry) : (d.inPath ? '#6366f1' : '#94a3b8'))
			.attr('stroke', 'white').attr('stroke-width', 1.5)
			.attr('filter', 'url(#node-shadow)');

		// Ministry label inside rect
		orgNodes.append('text')
			.attr('text-anchor', 'middle').attr('dominant-baseline', 'central')
			.attr('fill', 'white').attr('font-size', '10px').attr('font-weight', '600')
			.attr('pointer-events', 'none')
			.text(d => truncate(d.ministry ?? d.name, 11));

		// ── Name labels below nodes ─────────────────────────
		node.append('text')
			.attr('text-anchor', 'middle')
			.attr('y', d => d.type === 'person' ? nodeRadius(d) + 17 : 30)
			.attr('fill', '#1f2937').attr('font-size', '12px')
			.attr('font-weight', d => (d.isSource || d.isTarget) ? '700' : '500')
			.attr('pointer-events', 'none')
			.text(d => truncate(d.name, d.type === 'org' ? 18 : 22));

		// "Source" / "Target" annotation
		personNodes.filter(d => d.isSource || d.isTarget)
			.append('text')
			.attr('text-anchor', 'middle')
			.attr('y', d => nodeRadius(d) + 32)
			.attr('fill', d => d.isSource ? '#2563eb' : '#059669')
			.attr('font-size', '11px').attr('font-weight', '700').attr('letter-spacing', '0.3px')
			.attr('pointer-events', 'none')
			.text(d => d.isSource ? '▲ Source' : '▼ Target');

		// ── Tick ───────────────────────────────────────────
		simulation.on('tick', () => {
			// Persist positions for layout stability on re-render
			simNodes.forEach(n => {
				if (n.x != null && n.y != null) nodePositions.set(n.id, { x: n.x, y: n.y });
			});
			link
				.attr('x1', d => (d.source as GNode).x ?? 0).attr('y1', d => (d.source as GNode).y ?? 0)
				.attr('x2', d => (d.target as GNode).x ?? 0).attr('y2', d => (d.target as GNode).y ?? 0);
			node.attr('transform', d => `translate(${d.x ?? 0},${d.y ?? 0})`);
		});
	}

	// ---------------------------------------------------------------------------
	// Stats modal
	// ---------------------------------------------------------------------------
	let modalNode       = $state<GNode | null>(null);
	let modalNetwork    = $state<ColleagueNetwork | null>(null);
	let modalLoading    = $state(false);
	let ministryCounts  = $state<{ ministry: string; count: number }[]>([]);

	async function openModal(node: GNode) {
		modalNode = node; modalNetwork = null; ministryCounts = []; modalLoading = true;
		try {
			if (!node.person_id) return;
			const net = await fetchPersonNetwork(node.person_id);
			modalNetwork = net;
			const deg1 = net.colleagues_by_degree['1'] ?? [];
			const orgIds = [...new Set(deg1.flatMap(c => c.shared_organizations))];
			const roots = await Promise.all(orgIds.map(id => fetchRootMinistry(id)));
			const miniMap = new Map<string, number>();
			for (const c of deg1) {
				for (const oid of c.shared_organizations) {
					const idx = orgIds.indexOf(oid);
					const ministry = roots[idx]?.name ?? `Org ${oid}`;
					miniMap.set(ministry, (miniMap.get(ministry) ?? 0) + 1);
				}
			}
			ministryCounts = [...miniMap.entries()]
				.sort((a, b) => b[1] - a[1])
				.map(([ministry, count]) => ({ ministry, count }));
		} finally { modalLoading = false; }
	}

	function closeModal() { modalNode = null; }

	async function expandFromModal() {
		if (!modalNode) return;
		await expandNode(modalNode);
		closeModal();
	}

	// ---------------------------------------------------------------------------
	// Derived
	// ---------------------------------------------------------------------------
	const degreeBadge = $derived(
		pathResult && pathResult.nodes.length > 0
			? pathResult.nodes.filter(n => n.node_type === 'person').length - 1
			: null
	);

	const ministryLegend = $derived(
		[...new Set(graphNodes.map(n => n.ministry).filter(Boolean) as string[])]
			.map(m => ({ ministry: m, color: getMinistryColor(m) }))
	);
</script>

<div class="flex-1 flex flex-col lg:flex-row overflow-hidden" style="height: calc(100vh - 3.5rem - 49px)">

	<!-- ── Left sidebar ─────────────────────────────────── -->
	<aside class="w-full lg:w-80 xl:w-96 shrink-0 flex flex-col border-b lg:border-b-0 lg:border-r
	              border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 overflow-y-auto">

		<!-- Title + controls -->
		<div class="p-4 border-b border-gray-100 dark:border-gray-800 space-y-3">
			<div class="flex items-center justify-between">
				<h1 class="text-base font-semibold text-gray-900 dark:text-gray-100">Connectivity Explorer</h1>
				<InfoTip tip="Find the shortest connection path between two people. Click nodes to view stats and expand their network." />
			</div>

			<ConfidenceSlider bind:value={confidenceThreshold} />

			<label class="flex items-center gap-2 cursor-pointer group">
				<input type="checkbox" bind:checked={temporal}
					onchange={() => { if (source.selected && target.selected) findPath(); }}
					class="rounded accent-blue-600 w-3.5 h-3.5"/>
				<span class="text-sm text-gray-600 dark:text-gray-400 group-hover:text-gray-800 dark:group-hover:text-gray-200 transition-colors">
					Temporal (actual co-workers only)
				</span>
				<InfoTip tip="When on, only counts people who were physically working together at the same time. Turn off to find any historical connection." />
			</label>
		</div>

		<!-- Source slot -->
		<div class="p-4 border-b border-gray-100 dark:border-gray-800 space-y-3">
			<div class="flex items-center gap-1.5">
				<span class="w-2.5 h-2.5 rounded-full bg-blue-500 shrink-0"></span>
				<p class="text-sm font-semibold text-blue-600 dark:text-blue-400 uppercase tracking-wide">Source</p>
				<InfoTip tip="The person you're tracing the connection FROM. Name variants with scores above the threshold are included in the search." />
			</div>
			<PersonSearch
				placeholder="Search source person…"
				{confidenceThreshold}
				selected={source.selected}
				accentColor="blue"
				onselect={(p) => selectPerson(source, p)}
				onclear={() => clearSlot(source)}
			/>
			{#if source.selected && source.nameVariants.length > 0}
				<NameVariantZones
					nameVariants={source.nameVariants}
					activeNames={source.activeNames}
					{confidenceThreshold}
					inColor="blue"
					ontoggle={(name) => toggleVariant(source, name)}
				/>
			{/if}
		</div>

		<!-- Target slot -->
		<div class="p-4 space-y-3">
			<div class="flex items-center gap-1.5">
				<span class="w-2.5 h-2.5 rounded-full border-2 border-dashed border-emerald-500 shrink-0"></span>
				<p class="text-sm font-semibold text-emerald-600 dark:text-emerald-400 uppercase tracking-wide">Target</p>
				<InfoTip tip="The person you're tracing the connection TO. The graph shows how they are connected through shared organizations." />
			</div>
			<PersonSearch
				placeholder="Search target person…"
				{confidenceThreshold}
				selected={target.selected}
				accentColor="emerald"
				onselect={(p) => selectPerson(target, p)}
				onclear={() => clearSlot(target)}
			/>
			{#if target.selected && target.nameVariants.length > 0}
				<NameVariantZones
					nameVariants={target.nameVariants}
					activeNames={target.activeNames}
					{confidenceThreshold}
					inColor="emerald"
					ontoggle={(name) => toggleVariant(target, name)}
				/>
			{/if}
			{#if source.selected && target.selected}
				<button onclick={findPath} disabled={pathLoading}
					class="w-full py-2.5 text-sm font-semibold bg-blue-600 hover:bg-blue-700 text-white rounded-lg
					       transition-colors disabled:opacity-50 disabled:cursor-not-allowed mt-1">
					{pathLoading ? 'Searching…' : 'Find Connection'}
				</button>
			{/if}
		</div>
	</aside>

	<!-- ── Right panel — D3 canvas ───────────────────────── -->
	<section class="flex-1 relative flex flex-col bg-gray-50 dark:bg-gray-950 overflow-hidden">

		<!-- Status badge -->
		{#if pathResult || pathLoading || pathError}
			<div class="absolute top-4 left-1/2 -translate-x-1/2 z-10">
				{#if pathLoading}
					<div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700
					            rounded-full px-4 py-1.5 shadow-md text-sm text-gray-500 animate-pulse">
						Searching for connection…
					</div>
				{:else if pathError}
					<div class="bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800
					            rounded-full px-4 py-1.5 shadow-md text-sm text-red-600 dark:text-red-400">
						{pathError}
					</div>
				{:else if pathResult && pathResult.length === 0}
					<div class="bg-amber-50 dark:bg-amber-950 border border-amber-200 dark:border-amber-800
					            rounded-full px-4 py-1.5 shadow-md text-sm text-amber-700 dark:text-amber-400">
						No connection found — try disabling Temporal mode
					</div>
				{:else if pathResult}
					<div class="bg-white dark:bg-gray-900 border border-indigo-200 dark:border-indigo-800
					            rounded-full px-4 py-1.5 shadow-md flex items-center gap-2">
						<span class="w-2 h-2 rounded-full bg-indigo-500 animate-pulse"></span>
						<span class="text-sm font-semibold text-indigo-700 dark:text-indigo-400">
							{degreeBadge === 1 ? '1 degree' : `${degreeBadge} degrees`} of separation
						</span>
					</div>
				{/if}
			</div>
		{/if}

		<!-- Empty state -->
		{#if graphNodes.length === 0 && !pathLoading}
			<div class="absolute inset-0 flex items-center justify-center pointer-events-none">
				<div class="text-center space-y-2">
					<svg class="w-16 h-16 text-gray-200 dark:text-gray-700 mx-auto" fill="none" stroke="currentColor" stroke-width="1" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" d="M7.5 21L3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 12M21 7.5H7.5"/>
					</svg>
					{#if !source.selected && !target.selected}
						<p class="text-sm text-gray-400">Search for two people to find their connection</p>
					{:else if source.selected && !target.selected}
						<p class="text-sm text-gray-400">Now search for a target person</p>
					{:else if !source.selected && target.selected}
						<p class="text-sm text-gray-400">Now search for a source person</p>
					{:else}
						<p class="text-sm text-gray-400">Click "Find Connection" to search</p>
					{/if}
				</div>
			</div>
		{/if}

		<svg bind:this={svgEl} class="w-full h-full" style="touch-action: none;"></svg>

		<!-- Ministry legend -->
		{#if ministryLegend.length > 0}
			<div class="absolute bottom-4 left-4 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700
			            rounded-xl px-3 py-2.5 shadow-sm max-w-[180px]">
				<p class="text-[10px] font-semibold uppercase tracking-wide text-gray-400 mb-2">Ministry</p>
				<ul class="space-y-1.5">
					{#each ministryLegend as item}
						<li class="flex items-center gap-2">
							<span class="w-3 h-3 rounded-sm shrink-0" style="background: {item.color}"></span>
							<span class="text-xs text-gray-700 dark:text-gray-300 leading-tight truncate">{item.ministry}</span>
						</li>
					{/each}
				</ul>
			</div>
		{/if}

		<!-- Hint -->
		{#if graphNodes.length > 0}
			<div class="absolute bottom-4 right-4 text-xs text-gray-400 dark:text-gray-600
			            bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700
			            rounded-lg px-3 py-2 shadow-sm">
				Click a person to view network stats · Scroll to zoom · Drag to pan
			</div>
		{/if}
	</section>
</div>

<!-- ── Hover tooltip ─────────────────────────────────── -->
{#if hoveredNode}
	<div
		class="fixed z-30 pointer-events-none max-w-56 rounded-xl border border-gray-200 dark:border-gray-700
		       bg-white dark:bg-gray-900 shadow-xl px-3.5 py-2.5 space-y-1"
		style="left: {hoverClientX + 14}px; top: {hoverClientY - 60}px;"
	>
		<p class="text-sm font-semibold text-gray-900 dark:text-gray-100 leading-snug">{hoveredNode.name}</p>
		{#if hoveredNode.ministry}
			<div class="flex items-center gap-1.5">
				<span class="w-2.5 h-2.5 rounded-sm shrink-0" style="background: {getMinistryColor(hoveredNode.ministry)}"></span>
				<p class="text-xs text-gray-500 dark:text-gray-400 leading-snug">{hoveredNode.ministry}</p>
			</div>
		{/if}
		{#if hoveredNode.type === 'person'}
			<p class="text-xs text-gray-400 dark:text-gray-500">
				{hoveredNode.isSource ? '▲ Source' : hoveredNode.isTarget ? '▼ Target' : hoveredNode.inPath ? 'Path node' : 'Expanded'}
				{hoveredNode.type === 'person' ? '· Click for stats' : ''}
			</p>
		{:else}
			<p class="text-xs text-gray-400 dark:text-gray-500">Organisation node</p>
		{/if}
	</div>
{/if}

<!-- ── Node stats modal ─────────────────────────────── -->
{#if modalNode}
	<button
		class="fixed inset-0 z-40 bg-black/20 dark:bg-black/40 backdrop-blur-sm"
		onclick={closeModal}
		aria-label="Close modal"
	></button>

	<div class="fixed z-50 top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2
	            w-full max-w-sm bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700
	            rounded-2xl shadow-2xl p-6 space-y-4">

		<!-- Header -->
		<div class="flex items-start justify-between gap-3">
			<div class="flex items-center gap-3">
				<div class="w-11 h-11 rounded-full flex items-center justify-center text-white text-sm font-bold shrink-0"
				     style="background: {personFill(modalNode)}">
					{modalNode.name.slice(0, 2).toUpperCase()}
				</div>
				<div>
					<h2 class="font-semibold text-gray-900 dark:text-gray-100 text-base">{modalNode.name}</h2>
					{#if modalNode.ministry}
						<div class="flex items-center gap-1.5 mt-0.5">
							<span class="w-2 h-2 rounded-sm" style="background: {getMinistryColor(modalNode.ministry)}"></span>
							<p class="text-xs text-gray-500 dark:text-gray-400">{modalNode.ministry}</p>
						</div>
					{:else}
						<p class="text-xs {modalNode.isSource ? 'text-blue-500' : modalNode.isTarget ? 'text-emerald-500' : 'text-gray-400'}">
							{modalNode.isSource ? '▲ Source' : modalNode.isTarget ? '▼ Target' : modalNode.inPath ? 'In path' : 'Expanded node'}
						</p>
					{/if}
				</div>
			</div>
			<button onclick={closeModal}
				class="w-7 h-7 flex items-center justify-center rounded-lg text-gray-400
				       hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800
				       transition-colors shrink-0"
				aria-label="Close">
				<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/>
				</svg>
			</button>
		</div>

		{#if modalLoading}
			<div class="space-y-2">
				<div class="h-16 bg-gray-100 dark:bg-gray-800 rounded-xl animate-pulse"></div>
				<div class="h-28 bg-gray-100 dark:bg-gray-800 rounded-xl animate-pulse"></div>
			</div>
		{:else if modalNetwork}
			<div class="grid grid-cols-2 gap-3">
				<div class="bg-gray-50 dark:bg-gray-800 rounded-xl p-3 text-center">
					<p class="text-2xl font-bold text-gray-900 dark:text-gray-100 tabular-nums">
						{modalNetwork.summary.total_colleagues}
					</p>
					<p class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">Direct connections</p>
				</div>
				<div class="bg-gray-50 dark:bg-gray-800 rounded-xl p-3 text-center">
					<p class="text-2xl font-bold text-gray-900 dark:text-gray-100 tabular-nums">
						{ministryCounts.length}
					</p>
					<p class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
						{ministryCounts.length === 1 ? 'Ministry' : 'Ministries'}
					</p>
				</div>
			</div>

			{#if ministryCounts.length > 0}
				<div>
					<p class="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-2">Connections by ministry</p>
					<ul class="space-y-1.5 max-h-44 overflow-y-auto pr-1">
						{#each ministryCounts as m}
							<li class="flex items-center gap-2">
								<span class="w-3 h-3 rounded-sm shrink-0" style="background: {getMinistryColor(m.ministry)}"></span>
								<span class="text-sm text-gray-700 dark:text-gray-300 truncate flex-1">{m.ministry}</span>
								<span class="text-xs font-semibold tabular-nums shrink-0
								             bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400
								             rounded-full px-2 py-0.5">
									{m.count}
								</span>
							</li>
						{/each}
					</ul>
				</div>
			{/if}
		{/if}

		<button
			onclick={expandFromModal}
			disabled={modalLoading || modalNode.expanded}
			class="w-full py-2.5 text-sm font-semibold rounded-xl transition-colors
			       {modalNode.expanded
			         ? 'bg-gray-100 dark:bg-gray-800 text-gray-400 cursor-not-allowed'
			         : 'bg-indigo-600 hover:bg-indigo-700 text-white'}">
			{modalNode.expanded ? 'Already expanded' : 'Expand in graph'}
		</button>
	</div>
{/if}
