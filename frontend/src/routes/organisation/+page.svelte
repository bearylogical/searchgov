<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { organisations } from '$lib/api';
	import type { OrgResult } from '$lib/api';
	import { isAuthenticated, authReady } from '$lib/auth';
	import { goto } from '$app/navigation';
	import * as d3 from 'd3';

	$effect(() => {
		if ($authReady && !$isAuthenticated) goto('/login?redirect=/organisation');
	});

	// ── State ─────────────────────────────────────────────────────────────────
	let query = $state('');
	let results = $state<OrgResult[]>([]);
	let roots = $state<OrgResult[]>([]);
	let selected = $state<OrgResult | null>(null);
	let tree = $state<OrgResult[]>([]);
	let timeline = $state<string[]>([]);
	let selectedDate = $state('');
	let sliderIdx = $state(0);
	let searching = $state(false);
	let loadingTree = $state(false);
	let loadingRoots = $state(true);
	let searchError = $state('');
	let vizTruncated = $state(false);
	let vizEl = $state<HTMLDivElement | undefined>(); // $state for bind:this; tick() handles timing

	let debounceTimer: ReturnType<typeof setTimeout>;
	let sliderTimer: ReturnType<typeof setTimeout>;

	const MAX_VIZ_NODES = 300;

	// ── Lifecycle ─────────────────────────────────────────────────────────────
	onMount(async () => {
		try {
			roots = await organisations.roots();
		} catch {
			// silent — search still works
		} finally {
			loadingRoots = false;
		}
	});

	// ── Search ────────────────────────────────────────────────────────────────
	function onInput() {
		clearTimeout(debounceTimer);
		if (!query.trim()) {
			results = [];
			return;
		}
		debounceTimer = setTimeout(doSearch, 300);
	}

	async function doSearch() {
		searching = true;
		searchError = '';
		try {
			results = await organisations.search(query);
		} catch (e) {
			searchError = e instanceof Error ? e.message : 'Search failed';
			results = [];
		} finally {
			searching = false;
		}
	}

	// ── Org selection ─────────────────────────────────────────────────────────
	async function selectOrg(org: OrgResult) {
		selected = org;
		tree = [];
		timeline = [];
		selectedDate = '';
		loadingTree = true;
		try {
			[tree, timeline] = await Promise.all([
				organisations.tree(org.id),
				organisations.timeline(org.id)
			]);
			if (timeline.length) {
				sliderIdx = timeline.length - 1;
				selectedDate = timeline[sliderIdx];
			}
		} finally {
			loadingTree = false;
		}
	}

	// ── Snapshot slider ───────────────────────────────────────────────────────
	function onSliderInput() {
		selectedDate = timeline[sliderIdx];
		clearTimeout(sliderTimer);
		sliderTimer = setTimeout(reloadTree, 450);
	}

	async function reloadTree() {
		if (!selected) return;
		loadingTree = true;
		try {
			tree = await organisations.tree(selected.id, selectedDate);
		} finally {
			loadingTree = false;
		}
	}

	// ── Formatting ────────────────────────────────────────────────────────────
	function fmt(d: string) {
		return new Date(d).toLocaleDateString('en-SG', { year: 'numeric', month: 'short' });
	}

	// ── Metrics ───────────────────────────────────────────────────────────────
	let metrics = $derived.by(() => {
		if (!selected || !tree.length) return { total: 0, depth: 0, breadth: 0 };
		const childMap = new Map<number, number[]>();
		for (const n of tree) {
			const pid = n.parent_org_id ?? selected.id;
			if (!childMap.has(pid)) childMap.set(pid, []);
			childMap.get(pid)!.push(n.id);
		}
		let maxDepth = 0,
			maxBreadth = 0;
		const vis = new Set<number>([selected.id]);
		const queue: [number, number][] = [[selected.id, 0]];
		while (queue.length) {
			const [id, d] = queue.shift()!;
			const ch = childMap.get(id) ?? [];
			if (ch.length > maxBreadth) maxBreadth = ch.length;
			for (const c of ch) {
				if (!vis.has(c)) {
					vis.add(c);
					const nd = d + 1;
					if (nd > maxDepth) maxDepth = nd;
					queue.push([c, nd]);
				}
			}
		}
		return { total: tree.length, depth: maxDepth, breadth: maxBreadth };
	});

	// ── D3 tree ───────────────────────────────────────────────────────────────
	type TN = { id: string; pid: string | null; name: string };

	$effect(() => {
		// Capture reactive values synchronously so the async callback stays consistent
		const sel = selected;
		const currentTree = tree;
		const loading = loadingTree;
		if (!sel || loading || !currentTree.length) return;
		// tick() waits for Svelte to finish DOM updates (including bind:this on vizEl)
		tick().then(() => {
			if (!vizEl) return;
			vizTruncated = renderTree(vizEl, sel, currentTree);
		});
	});

	function renderTree(container: HTMLDivElement, root: OrgResult, desc: OrgResult[]): boolean {
		// Build deduplicated node list
		const seen = new Set<string>();
		const nodes: TN[] = [];
		const add = (n: TN) => {
			if (!seen.has(n.id)) {
				seen.add(n.id);
				nodes.push(n);
			}
		};
		add({ id: String(root.id), pid: null, name: root.name });
		for (const d of desc) {
			add({ id: String(d.id), pid: String(d.parent_org_id ?? root.id), name: d.name });
		}

		// BFS-cap to MAX_VIZ_NODES
		let display = nodes;
		let truncated = false;
		if (nodes.length > MAX_VIZ_NODES) {
			truncated = true;
			const pmap = new Map<string, TN[]>();
			for (const n of nodes) {
				if (n.pid) {
					const arr = pmap.get(n.pid) ?? [];
					arr.push(n);
					pmap.set(n.pid, arr);
				}
			}
			display = [nodes[0]];
			const q = [nodes[0].id];
			let qi = 0;
			while (qi < q.length && display.length < MAX_VIZ_NODES) {
				const pid = q[qi++];
				for (const ch of pmap.get(pid) ?? []) {
					if (display.length >= MAX_VIZ_NODES) break;
					display.push(ch);
					q.push(ch.id);
				}
			}
		}

		// Stratify
		let hier: d3.HierarchyNode<TN>;
		try {
			hier = d3.stratify<TN>().id((n) => n.id).parentId((n) => n.pid)(display);
		} catch {
			return truncated;
		}

		const W = container.clientWidth || 800;
		const H = 520;
		const nCount = hier.descendants().length;
		const nodeSpacing = Math.max(14, Math.min(22, 3200 / nCount));

		container.innerHTML = '';

		const svg = d3
			.select(container)
			.append('svg')
			.attr('width', W)
			.attr('height', H)
			.style('display', 'block')
			.style('cursor', 'grab');

		const g = svg.append('g');

		// Zoom / pan
		const zoom = d3
			.zoom<SVGSVGElement, unknown>()
			.scaleExtent([0.1, 4])
			.on('zoom', (e) => g.attr('transform', e.transform.toString()));
		// eslint-disable-next-line @typescript-eslint/no-explicit-any
		(svg as any).call(zoom);

		// Tree layout
		d3.tree<TN>().nodeSize([nodeSpacing, 210])(hier);

		const palette = ['#7c3aed', '#8b5cf6', '#a78bfa', '#c4b5fd', '#ede9fe'];

		// Links
		g.selectAll('path.link')
			.data(hier.links())
			.join('path')
			.attr('class', 'link')
			.attr('fill', 'none')
			.attr('stroke', '#e5e7eb')
			.attr('stroke-width', 1)
			// eslint-disable-next-line @typescript-eslint/no-explicit-any
			.attr('d', (d3.linkHorizontal() as any).x((d: any) => d.y).y((d: any) => d.x));

		// Node groups
		const nodeG = g
			.selectAll('g.node')
			.data(hier.descendants())
			.join('g')
			.attr('class', 'node')
			// eslint-disable-next-line @typescript-eslint/no-explicit-any
			.attr('transform', (d: any) => `translate(${d.y},${d.x})`);

		nodeG
			.append('circle')
			// eslint-disable-next-line @typescript-eslint/no-explicit-any
			.attr('r', (d: any) => (d.depth === 0 ? 7 : d.depth === 1 ? 5 : 3))
			// eslint-disable-next-line @typescript-eslint/no-explicit-any
			.attr('fill', (d: any) => palette[Math.min(d.depth, palette.length - 1)])
			.attr('stroke', '#fff')
			.attr('stroke-width', 1.5);

		nodeG
			.append('title')
			.text((d) => d.data.name);

		nodeG
			.append('text')
			// eslint-disable-next-line @typescript-eslint/no-explicit-any
			.attr('x', (d: any) => (d.children ? -10 : 10))
			.attr('dy', '0.35em')
			// eslint-disable-next-line @typescript-eslint/no-explicit-any
			.attr('text-anchor', (d: any) => (d.children ? 'end' : 'start'))
			.attr('font-size', 10)
			.attr('fill', '#4b5563')
			.text((d) => {
				const n = d.data.name;
				return n.length > 30 ? n.slice(0, 30) + '…' : n;
			});

		// Fit to view after layout
		requestAnimationFrame(() => {
			const bb = (g.node() as SVGGElement)?.getBBox();
			if (!bb?.width) return;
			const pad = 36;
			const sc = Math.min((W - pad) / bb.width, (H - pad) / bb.height, 0.95);
			const tx = pad / 2 - bb.x * sc;
			const ty = H / 2 - (bb.y + bb.height / 2) * sc;
			// eslint-disable-next-line @typescript-eslint/no-explicit-any
			(svg as any).call(zoom.transform, d3.zoomIdentity.translate(tx, ty).scale(sc));
		});

		return truncated;
	}

	// ── Sidebar helpers ───────────────────────────────────────────────────────
	let sidebarItems = $derived(query.trim() ? results : roots);
	let showMinHeader = $derived(!query.trim() && !loadingRoots);
</script>

<div
	class="flex-1 flex flex-col lg:flex-row overflow-hidden"
	style="height: calc(100vh - 3.5rem - 49px)"
>
	<!-- ── Left sidebar ─────────────────────────────────────────────────────── -->
	<aside
		class="w-full lg:w-72 xl:w-80 shrink-0 flex flex-col border-b lg:border-b-0 lg:border-r border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900"
	>
		<!-- Search header -->
		<div class="p-4 border-b border-gray-100 dark:border-gray-800">
			<h1 class="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">
				Organisation Explorer
			</h1>
			<div class="relative">
				<svg
					class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none"
					fill="none"
					stroke="currentColor"
					stroke-width="2"
					viewBox="0 0 24 24"
				>
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z"
					/>
				</svg>
				<input
					type="text"
					placeholder="Search organisations…"
					bind:value={query}
					oninput={onInput}
					class="w-full pl-9 pr-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg text-sm
					       bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 placeholder-gray-400
					       focus:outline-none focus:ring-2 focus:ring-violet-500/20 focus:border-violet-500 transition-colors"
				/>
			</div>
		</div>

		<!-- Section label -->
		{#if showMinHeader}
			<div
				class="px-4 py-2 bg-gray-50 dark:bg-gray-800/50 border-b border-gray-100 dark:border-gray-800 flex items-center justify-between"
			>
				<span class="text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500"
					>Ministries</span
				>
				{#if roots.length}
					<span class="text-xs text-gray-400">{roots.length}</span>
				{/if}
			</div>
		{/if}

		<!-- List -->
		<div class="flex-1 overflow-y-auto">
			{#if (loadingRoots && !query) || searching}
				<div class="p-3 space-y-1">
					{#each Array(7) as _}
						<div class="h-11 bg-gray-100 dark:bg-gray-800 rounded-lg animate-pulse"></div>
					{/each}
				</div>
			{:else if searchError}
				<div class="p-4">
					<p class="text-sm text-red-500">{searchError}</p>
				</div>
			{:else if query && !results.length}
				<div class="p-8 text-center">
					<svg
						class="w-7 h-7 text-gray-300 dark:text-gray-600 mx-auto mb-2"
						fill="none"
						stroke="currentColor"
						stroke-width="1.5"
						viewBox="0 0 24 24"
					>
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							d="M15.75 15.75l-2.489-2.489m0 0a3.375 3.375 0 10-4.773-4.773 3.375 3.375 0 004.774 4.774zM21 12a9 9 0 11-18 0 9 9 0 0118 0z"
						/>
					</svg>
					<p class="text-sm text-gray-400 dark:text-gray-500">No results for "{query}"</p>
				</div>
			{:else}
				<ul class="py-1">
					{#each sidebarItems as org (org.id)}
						<li>
							<button
								onclick={() => selectOrg(org)}
								class="w-full text-left px-3 py-2.5 flex items-center gap-3 transition-colors
								       hover:bg-gray-50 dark:hover:bg-gray-800
								       {selected?.id === org.id
									? 'bg-violet-50 dark:bg-violet-900/20 border-r-2 border-violet-500'
									: ''}"
							>
								<div
									class="w-7 h-7 rounded-md flex items-center justify-center shrink-0 transition-colors
									       {selected?.id === org.id
										? 'bg-violet-600'
										: 'bg-gray-100 dark:bg-gray-800'}"
								>
									<svg
										class="w-3.5 h-3.5 {selected?.id === org.id
											? 'text-white'
											: 'text-gray-500 dark:text-gray-400'}"
										fill="none"
										stroke="currentColor"
										stroke-width="1.5"
										viewBox="0 0 24 24"
									>
										<path
											stroke-linecap="round"
											stroke-linejoin="round"
											d="M3.75 21h16.5M4.5 3h15M5.25 3v18m13.5-18v18M9 6.75h1.5m-1.5 3h1.5m-1.5 3h1.5m3-6H15m-1.5 3H15m-1.5 3H15M9 21v-3.375c0-.621.504-1.125 1.125-1.125h3.75c.621 0 1.125.504 1.125 1.125V21"
										/>
									</svg>
								</div>
								<div class="min-w-0 flex-1">
									<p
										class="text-sm font-medium truncate leading-tight
										       {selected?.id === org.id
											? 'text-violet-700 dark:text-violet-300'
											: 'text-gray-900 dark:text-gray-100'}"
									>
										{org.name}
									</p>
									{#if org.department}
										<p class="text-xs text-gray-400 dark:text-gray-500 truncate mt-0.5">
											{org.department}
										</p>
									{/if}
								</div>
							</button>
						</li>
					{/each}
				</ul>
			{/if}
		</div>
	</aside>

	<!-- ── Right panel ──────────────────────────────────────────────────────── -->
	<section class="flex-1 overflow-y-auto bg-gray-50 dark:bg-gray-950">
		{#if !selected}
			<!-- Welcome state -->
			<div class="h-full flex items-center justify-center p-8">
				<div class="text-center max-w-xs">
					<div
						class="w-16 h-16 rounded-2xl bg-violet-100 dark:bg-violet-900/30 flex items-center justify-center mx-auto mb-4"
					>
						<svg
							class="w-8 h-8 text-violet-500"
							fill="none"
							stroke="currentColor"
							stroke-width="1.5"
							viewBox="0 0 24 24"
						>
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								d="M2.25 21h19.5m-18-18v18m10.5-18v18m6-13.5V21M6.75 6.75h.75m-.75 3h.75m-.75 3h.75m3-6h.75m-.75 3h.75m-.75 3h.75M6.75 21v-3.375c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21M3 3h12m-.75 4.5H21"
							/>
						</svg>
					</div>
					<h2 class="text-base font-semibold text-gray-700 dark:text-gray-300 mb-1">
						Select a Ministry
					</h2>
					<p class="text-sm text-gray-400 dark:text-gray-500 leading-relaxed">
						Choose a ministry from the sidebar or search to explore its hierarchy, visualise the
						structure, and track changes over time.
					</p>
				</div>
			</div>
		{:else}
			<div class="p-5 space-y-4 max-w-5xl mx-auto">
				<!-- Org header -->
				<div
					class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl p-4 shadow-sm"
				>
					<div class="flex items-center gap-3">
						<div
							class="w-10 h-10 rounded-xl bg-violet-600 flex items-center justify-center shrink-0"
						>
							<svg
								class="w-5 h-5 text-white"
								fill="none"
								stroke="currentColor"
								stroke-width="1.5"
								viewBox="0 0 24 24"
							>
								<path
									stroke-linecap="round"
									stroke-linejoin="round"
									d="M3.75 21h16.5M4.5 3h15M5.25 3v18m13.5-18v18M9 6.75h1.5m-1.5 3h1.5m-1.5 3h1.5m3-6H15m-1.5 3H15m-1.5 3H15M9 21v-3.375c0-.621.504-1.125 1.125-1.125h3.75c.621 0 1.125.504 1.125 1.125V21"
								/>
							</svg>
						</div>
						<div class="min-w-0 flex-1">
							<h2 class="text-base font-semibold text-gray-900 dark:text-gray-100">
								{selected.name}
							</h2>
							{#if selected.department}
								<p class="text-sm text-gray-500 dark:text-gray-400">{selected.department}</p>
							{/if}
						</div>
						{#if selectedDate}
							<span
								class="text-xs bg-violet-100 dark:bg-violet-900/30 text-violet-700 dark:text-violet-300
								       px-2.5 py-1 rounded-full font-medium shrink-0"
							>
								{fmt(selectedDate)}
							</span>
						{/if}
					</div>
				</div>

				<!-- Stats cards -->
				<div class="grid grid-cols-3 gap-3">
					<!-- Sub-agencies -->
					<div
						class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl p-4 shadow-sm"
					>
						{#if loadingTree}
							<div
								class="h-8 w-16 bg-gray-100 dark:bg-gray-800 rounded-lg animate-pulse mb-1"
							></div>
						{:else}
							<div class="text-2xl font-bold text-violet-600">
								{metrics.total.toLocaleString()}
							</div>
						{/if}
						<div class="text-xs font-medium text-gray-600 dark:text-gray-400 mt-1">
							Sub-agencies
						</div>
						<div class="text-xs text-gray-400 dark:text-gray-600 mt-0.5">Total units</div>
					</div>

					<!-- Hierarchy depth -->
					<div
						class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl p-4 shadow-sm"
					>
						{#if loadingTree}
							<div
								class="h-8 w-10 bg-gray-100 dark:bg-gray-800 rounded-lg animate-pulse mb-1"
							></div>
						{:else}
							<div class="text-2xl font-bold text-blue-600">{metrics.depth}</div>
						{/if}
						<div class="text-xs font-medium text-gray-600 dark:text-gray-400 mt-1">
							Hierarchy depth
						</div>
						<div class="text-xs text-gray-400 dark:text-gray-600 mt-0.5">Levels below root</div>
					</div>

					<!-- Snapshots -->
					<div
						class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl p-4 shadow-sm"
					>
						<div class="text-2xl font-bold text-emerald-600">{timeline.length}</div>
						<div class="text-xs font-medium text-gray-600 dark:text-gray-400 mt-1">Snapshots</div>
						<div class="text-xs text-gray-400 dark:text-gray-600 mt-0.5">
							{#if timeline.length > 1}
								{fmt(timeline[0])} – {fmt(timeline[timeline.length - 1])}
							{:else if timeline.length === 1}
								{fmt(timeline[0])}
							{:else}
								No data
							{/if}
						</div>
					</div>
				</div>

				<!-- D3 hierarchy map -->
				<div
					class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl shadow-sm overflow-hidden"
				>
					<div
						class="px-4 py-3 border-b border-gray-100 dark:border-gray-800 flex items-center justify-between"
					>
						<div class="flex items-center gap-2">
							<h3 class="text-sm font-medium text-gray-900 dark:text-gray-100">Hierarchy Map</h3>
							<span class="text-xs text-gray-400 dark:text-gray-500"
								>scroll to zoom · drag to pan</span
							>
						</div>
						{#if vizTruncated}
							<span
								class="text-xs text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 px-2 py-0.5 rounded-full"
							>
								Showing first {MAX_VIZ_NODES} of {metrics.total + 1} nodes
							</span>
						{/if}
					</div>
					<div class="relative" style="height: 520px">
						{#if loadingTree}
							<div class="absolute inset-0 flex items-center justify-center">
								<div class="flex flex-col items-center gap-3">
									<div
										class="w-8 h-8 border-[3px] border-violet-500 border-t-transparent rounded-full animate-spin"
									></div>
									<p class="text-sm text-gray-400">Loading hierarchy…</p>
								</div>
							</div>
						{:else if !tree.length}
							<div class="absolute inset-0 flex items-center justify-center">
								<p class="text-sm text-gray-400 dark:text-gray-500">
									No sub-organisations at this snapshot
								</p>
							</div>
						{:else}
							<div bind:this={vizEl} class="w-full h-full"></div>
						{/if}
					</div>
				</div>

				<!-- Timeline slider -->
				{#if timeline.length > 1}
					<div
						class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl p-4 shadow-sm"
					>
						<div class="flex items-center justify-between mb-3">
							<div>
								<span class="text-xs font-medium text-gray-600 dark:text-gray-400"
									>Snapshot date</span
								>
								{#if loadingTree}
									<div
										class="h-4 w-24 bg-gray-100 dark:bg-gray-800 rounded animate-pulse mt-1"
									></div>
								{:else}
									<p class="text-sm font-semibold text-violet-600 mt-0.5">{fmt(selectedDate)}</p>
								{/if}
							</div>
							<span class="text-xs text-gray-400 dark:text-gray-500 tabular-nums">
								{sliderIdx + 1} / {timeline.length}
							</span>
						</div>
						<input
							type="range"
							min="0"
							max={timeline.length - 1}
							bind:value={sliderIdx}
							oninput={onSliderInput}
							class="w-full h-1.5 rounded-full appearance-none cursor-pointer accent-violet-600"
						/>
						<div class="flex justify-between mt-2">
							<span class="text-xs text-gray-400 dark:text-gray-500">{fmt(timeline[0])}</span>
							<span class="text-xs text-gray-400 dark:text-gray-500"
								>{fmt(timeline[timeline.length - 1])}</span
							>
						</div>
					</div>
				{/if}

				<!-- Sub-org list -->
				{#if !loadingTree && tree.length > 0}
					<div>
						<h3
							class="text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500 px-1 mb-2"
						>
							All Sub-agencies ({tree.length.toLocaleString()})
						</h3>
						<ul class="space-y-1.5">
							{#each tree as child (child.id)}
								<li
									class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg
									       px-4 py-3 shadow-sm flex items-center gap-3 hover:shadow-md transition-shadow"
								>
									<div
										class="w-1 h-6 rounded-full bg-violet-200 dark:bg-violet-800 shrink-0"
									></div>
									<div class="min-w-0 flex-1">
										<p
											class="text-sm font-medium text-gray-900 dark:text-gray-100 truncate"
										>
											{child.name}
										</p>
										{#if child.department}
											<p class="text-xs text-gray-400 dark:text-gray-500 mt-0.5 truncate">
												{child.department}
											</p>
										{/if}
									</div>
								</li>
							{/each}
						</ul>
					</div>
				{/if}
			</div>
		{/if}
	</section>
</div>
