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

	$effect(() => {
		if ($authReady && !$isAuthenticated) goto('/login?redirect=/connectivity');
	});

	// ---------------------------------------------------------------------------
	// Person slot — one for source, one for target
	// ---------------------------------------------------------------------------
	interface PersonSlot {
		selected: PersonResult | null;
		nameVariants: NameVariant[];
		career: EmploymentEntry[];
		/** Variant names currently included (drives both timeline filter and path IDs). */
		activeNames: Set<string>;
		loading: boolean;
		error: string;
	}

	function makeSlot(): PersonSlot {
		return {
			selected: null, nameVariants: [], career: [],
			activeNames: new Set(), loading: false, error: ''
		};
	}

	let source = $state<PersonSlot>(makeSlot());
	let target = $state<PersonSlot>(makeSlot());
	let confidenceThreshold = $state(95);

	// Derive the person IDs to use for path-finding from active variant names.
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

	// ---------------------------------------------------------------------------
	// Select person
	// ---------------------------------------------------------------------------
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
		// Auto-trigger path search when both are ready.
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
	}

	// ---------------------------------------------------------------------------
	// D3 Graph state
	// ---------------------------------------------------------------------------
	interface GNode extends d3.SimulationNodeDatum {
		id: string;
		type: 'person' | 'org';
		name: string;
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

	// ---------------------------------------------------------------------------
	// Path finding
	// ---------------------------------------------------------------------------
	async function findPath() {
		if (!source.selected || !target.selected) return;
		pathLoading = true; pathError = '';
		try {
			pathResult = await graph.path(activeIds(source), activeIds(target), temporal);
			buildGraphFromPath(pathResult.nodes);
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

	// ---------------------------------------------------------------------------
	// Node expansion
	// ---------------------------------------------------------------------------
	const networkCache = new Map<number, ColleagueNetwork>();
	const orgCache     = new Map<number, OrgResult>();

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
		const anchorX = graphNodes.find(n => n.id === node.id)?.x ?? 0;
		const anchorY = graphNodes.find(n => n.id === node.id)?.y ?? 0;

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
						isSource: false, isTarget: false, expanded: false
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

	function nodeRadius(d: GNode) {
		if (d.isSource || d.isTarget) return 24;
		return d.inPath && d.type === 'person' ? 18 : 14;
	}

	function truncate(s: string, max: number) {
		return s.length > max ? s.slice(0, max - 1) + '…' : s;
	}

	function renderD3() {
		if (!svgEl) return;
		const svg = d3.select(svgEl);
		svg.selectAll('*').remove();

		const g = svg.append('g');

		svg.call(
			d3.zoom<SVGSVGElement, unknown>()
				.scaleExtent([0.2, 4])
				.on('zoom', e => g.attr('transform', e.transform))
		);

		// Deep-copy so D3 mutations don't bleed into $state
		const simNodes: GNode[] = graphNodes.map(n => ({ ...n }));
		const simEdges: GEdge[] = graphEdges.map(e => ({
			source: typeof e.source === 'string' ? e.source : (e.source as GNode).id,
			target: typeof e.target === 'string' ? e.target : (e.target as GNode).id,
			inPath: e.inPath
		}));

		simulation = d3.forceSimulation<GNode>(simNodes)
			.force('link', d3.forceLink<GNode, GEdge>(simEdges).id(d => d.id).distance(d => d.inPath ? 130 : 90))
			.force('charge', d3.forceManyBody().strength(-350))
			.force('center', d3.forceCenter(svgWidth / 2, svgHeight / 2))
			.force('collide', d3.forceCollide<GNode>(d => nodeRadius(d) + 8));

		const link = g.append('g')
			.selectAll<SVGLineElement, GEdge>('line')
			.data(simEdges)
			.join('line')
			.attr('stroke', d => d.inPath ? '#3b82f6' : '#cbd5e1')
			.attr('stroke-width', d => d.inPath ? 2.5 : 1.2)
			.attr('stroke-dasharray', d => d.inPath ? null : '4,3')
			.attr('opacity', d => d.inPath ? 1 : 0.6);

		const drag = d3.drag<SVGGElement, GNode>()
			.on('start', (event, d) => { if (!event.active) simulation?.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
			.on('drag',  (event, d) => { d.fx = event.x; d.fy = event.y; })
			.on('end',   (event, d) => { if (!event.active) simulation?.alphaTarget(0); d.fx = null; d.fy = null; });

		const node = g.append('g')
			.selectAll<SVGGElement, GNode>('g')
			.data(simNodes)
			.join('g')
			.style('cursor', d => d.type === 'person' ? 'pointer' : 'default')
			.call(drag)
			.on('click', (_e, d) => { if (d.type === 'person') openModal(d); });

		// Person circles
		node.filter(d => d.type === 'person')
			.append('circle')
			.attr('r', nodeRadius)
			.attr('fill', d => (d.isSource || d.isTarget) ? '#2563eb' : d.inPath ? '#3b82f6' : '#94a3b8')
			.attr('stroke', d => d.expanded ? '#fbbf24' : (d.isSource || d.isTarget ? '#1d4ed8' : 'white'))
			.attr('stroke-width', d => d.expanded ? 3 : 2)
			.attr('opacity', 0.9);

		// Org rectangles
		node.filter(d => d.type === 'org')
			.append('rect')
			.attr('x', -24).attr('y', -12).attr('width', 48).attr('height', 24).attr('rx', 6)
			.attr('fill', d => d.inPath ? '#0d9488' : '#94a3b8')
			.attr('opacity', 0.85)
			.attr('stroke', 'white').attr('stroke-width', 1.5);

		// Initials inside person circles
		node.filter(d => d.type === 'person')
			.append('text')
			.attr('text-anchor', 'middle').attr('dominant-baseline', 'central')
			.attr('fill', 'white').attr('font-size', '10px').attr('font-weight', '600')
			.attr('pointer-events', 'none')
			.text(d => d.name.slice(0, 2).toUpperCase());

		// Org label inside rect
		node.filter(d => d.type === 'org')
			.append('text')
			.attr('text-anchor', 'middle').attr('dominant-baseline', 'central')
			.attr('fill', 'white').attr('font-size', '8px').attr('font-weight', '500')
			.attr('pointer-events', 'none')
			.text(d => truncate(d.name, 8));

		// Name labels below nodes
		node.append('text')
			.attr('text-anchor', 'middle')
			.attr('y', d => d.type === 'person' ? nodeRadius(d) + 14 : 28)
			.attr('fill', '#374151').attr('font-size', '10px')
			.attr('font-weight', d => (d.isSource || d.isTarget) ? '700' : '400')
			.text(d => truncate(d.name, d.type === 'org' ? 14 : 18));

		simulation.on('tick', () => {
			link
				.attr('x1', d => (d.source as GNode).x ?? 0)
				.attr('y1', d => (d.source as GNode).y ?? 0)
				.attr('x2', d => (d.target as GNode).x ?? 0)
				.attr('y2', d => (d.target as GNode).y ?? 0);
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
			const orgData = await fetchOrgsForMinistries(orgIds);
			const miniMap = new Map<string, number>();
			for (const c of deg1) {
				for (const oid of c.shared_organizations) {
					const org = orgData.get(oid);
					const ministry = org?.department ?? org?.name ?? `Org ${oid}`;
					miniMap.set(ministry, (miniMap.get(ministry) ?? 0) + 1);
				}
			}
			ministryCounts = [...miniMap.entries()]
				.sort((a, b) => b[1] - a[1])
				.map(([ministry, count]) => ({ ministry, count }));
		} finally { modalLoading = false; }
	}

	async function fetchOrgsForMinistries(orgIds: number[]): Promise<Map<number, OrgResult>> {
		const result = new Map<number, OrgResult>();
		await Promise.all(orgIds.map(async id => {
			if (orgCache.has(id)) { result.set(id, orgCache.get(id)!); return; }
			try {
				const tree = await organisations.tree(id);
				if (tree.length > 0) { orgCache.set(id, tree[0]); result.set(id, tree[0]); }
			} catch { /* skip */ }
		}));
		return result;
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
	const degreeBadge = $derived(() => {
		if (!pathResult || pathResult.length === 0) return null;
		return pathResult.nodes.filter(n => n.node_type === 'person').length - 1;
	});
</script>

<div class="flex-1 flex flex-col lg:flex-row overflow-hidden" style="height: calc(100vh - 3.5rem - 49px)">

	<!-- ── Left sidebar ─────────────────────────────────── -->
	<aside class="w-full lg:w-80 xl:w-96 shrink-0 flex flex-col border-b lg:border-b-0 lg:border-r border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 overflow-y-auto">

		<!-- Global controls -->
		<div class="p-4 border-b border-gray-100 dark:border-gray-800 space-y-3">
			<h1 class="text-sm font-semibold text-gray-900 dark:text-gray-100">Connectivity Explorer</h1>
			<ConfidenceSlider bind:value={confidenceThreshold} />
			<label class="flex items-center gap-2 cursor-pointer">
				<input type="checkbox" bind:checked={temporal}
					onchange={() => { if (source.selected && target.selected) findPath(); }}
					class="rounded accent-blue-600"/>
				<span class="text-xs text-gray-600 dark:text-gray-400">Temporal only (actual co-workers)</span>
			</label>
		</div>

		<!-- Source slot -->
		<div class="p-4 border-b border-gray-100 dark:border-gray-800 space-y-3">
			<p class="text-xs font-semibold text-blue-600 dark:text-blue-400 uppercase tracking-wide">Source</p>
			<PersonSearch
				placeholder="Search source…"
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
			<p class="text-xs font-semibold text-emerald-600 dark:text-emerald-400 uppercase tracking-wide">Target</p>
			<PersonSearch
				placeholder="Search target…"
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
					class="w-full py-2 text-sm font-semibold bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors disabled:opacity-50">
					{pathLoading ? 'Finding…' : 'Find Connection'}
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
					<div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-full px-4 py-1.5 shadow text-sm text-gray-500 animate-pulse">
						Searching…
					</div>
				{:else if pathError}
					<div class="bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 rounded-full px-4 py-1.5 shadow text-sm text-red-600 dark:text-red-400">
						{pathError}
					</div>
				{:else if pathResult && pathResult.length === 0}
					<div class="bg-amber-50 dark:bg-amber-950 border border-amber-200 dark:border-amber-800 rounded-full px-4 py-1.5 shadow text-sm text-amber-700 dark:text-amber-400">
						No connection found — try disabling temporal mode
					</div>
				{:else if pathResult}
					{@const deg = degreeBadge()}
					<div class="bg-white dark:bg-gray-900 border border-blue-200 dark:border-blue-800 rounded-full px-4 py-1.5 shadow flex items-center gap-2">
						<span class="w-2 h-2 rounded-full bg-blue-500 animate-pulse"></span>
						<span class="text-sm font-semibold text-blue-700 dark:text-blue-400">
							{deg === 1 ? '1 degree' : `${deg} degrees`} of separation
						</span>
					</div>
				{/if}
			</div>
		{/if}

		<!-- Empty state -->
		{#if graphNodes.length === 0 && !pathLoading}
			<div class="absolute inset-0 flex items-center justify-center pointer-events-none">
				<div class="text-center">
					<svg class="w-16 h-16 text-gray-200 dark:text-gray-700 mx-auto mb-3" fill="none" stroke="currentColor" stroke-width="1" viewBox="0 0 24 24">
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

		{#if graphNodes.length > 0}
			<div class="absolute bottom-4 right-4 text-xs text-gray-400 dark:text-gray-600
			            bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700
			            rounded-lg px-3 py-2 shadow-sm">
				Click a person node to see their network stats
			</div>
		{/if}
	</section>
</div>

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
				<div class="w-10 h-10 rounded-full bg-blue-600 flex items-center justify-center text-white font-bold">
					{modalNode.name.slice(0, 2).toUpperCase()}
				</div>
				<div>
					<h2 class="font-semibold text-gray-900 dark:text-gray-100">{modalNode.name}</h2>
					<p class="text-xs {modalNode.isSource ? 'text-blue-500' : modalNode.isTarget ? 'text-emerald-500' : modalNode.inPath ? 'text-blue-400' : 'text-gray-400'}">
						{modalNode.isSource ? 'Source' : modalNode.isTarget ? 'Target' : modalNode.inPath ? 'In path' : 'Expanded node'}
					</p>
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
			<!-- Stats -->
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

			<!-- Ministry breakdown -->
			{#if ministryCounts.length > 0}
				<div>
					<p class="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">Connections by ministry</p>
					<ul class="space-y-1.5 max-h-40 overflow-y-auto pr-1">
						{#each ministryCounts as m}
							<li class="flex items-center justify-between gap-2">
								<span class="text-sm text-gray-700 dark:text-gray-300 truncate">{m.ministry}</span>
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
			         : 'bg-blue-600 hover:bg-blue-700 text-white'}">
			{modalNode.expanded ? 'Already expanded' : 'Expand in graph'}
		</button>
	</div>
{/if}
