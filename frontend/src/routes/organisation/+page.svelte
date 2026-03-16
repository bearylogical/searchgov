<script lang="ts">
	import { onMount } from 'svelte';
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
	let headcount = $state<number | null>(null);
	let loadingHeadcount = $state(false);
	let vizTruncated = $state(false);
	let vizEl = $state<HTMLDivElement | undefined>();
	let vizSearch = $state('');
	let expandedIds = $state(new Set<string>());
	let sidebarCollapsed = $state(false); // mobile collapse

	let debounceTimer: ReturnType<typeof setTimeout>;
	let sliderTimer: ReturnType<typeof setTimeout>;

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
		vizSearch = '';
		expandedIds = new Set();
		selectedDate = '';
		headcount = null;
		loadingTree = true;
		// Auto-collapse sidebar on mobile after selection
		if (window.innerWidth < 1024) sidebarCollapsed = true;
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
		fetchHeadcount(org.id, selectedDate);
	}

	async function fetchHeadcount(orgId: number, date: string) {
		if (!date) return;
		loadingHeadcount = true;
		try {
			const res = await organisations.headcount(orgId, date);
			headcount = res.headcount;
		} catch {
			headcount = null;
		} finally {
			loadingHeadcount = false;
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
		fetchHeadcount(selected.id, selectedDate);
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

	// ── Year ticks for slider ─────────────────────────────────────────────────
	let yearTicks = $derived.by(() => {
		if (timeline.length < 2) return [] as { year: number; pct: number }[];
		const seen = new Set<number>();
		const ticks: { year: number; pct: number }[] = [];
		for (let i = 0; i < timeline.length; i++) {
			const year = new Date(timeline[i]).getFullYear();
			if (!seen.has(year)) {
				seen.add(year);
				ticks.push({ year, pct: (i / (timeline.length - 1)) * 100 });
			}
		}
		return ticks;
	});

	// ── D3 tree ───────────────────────────────────────────────────────────────
	type TN = { id: string; pid: string | null; name: string };

	$effect(() => {
		const el = vizEl;
		const sel = selected;
		const currentTree = tree;
		const loading = loadingTree;
		const q = vizSearch;
		const expanded = expandedIds;
		if (!el || !sel || loading || !currentTree.length) return;
		vizTruncated = renderTree(el, sel, currentTree, q, expanded);
	});

	function renderTree(container: HTMLDivElement, root: OrgResult, desc: OrgResult[], highlight = '', expanded: Set<string> = new Set()): boolean {
		const q = highlight.trim().toLowerCase();
		const shortName = (n: string) => n.split(':').pop()?.trim() ?? n;

		const wrapLines = (text: string, maxChars: number): string[] => {
			const words = text.split(/\s+/);
			const lines: string[] = [];
			let cur = '';
			for (const w of words) {
				const next = cur ? `${cur} ${w}` : w;
				if (cur && next.length > maxChars) { lines.push(cur); cur = w; }
				else cur = next;
			}
			if (cur) lines.push(cur);
			return lines;
		};

		const seen = new Set<string>();
		const rawNodes: TN[] = [];
		const add = (n: TN) => { if (!seen.has(n.id)) { seen.add(n.id); rawNodes.push(n); } };
		add({ id: String(root.id), pid: null, name: root.name });
		const validIds = new Set<string>([String(root.id)]);
		for (const d of desc) validIds.add(String(d.id));
		for (const d of desc) {
			const rawPid = d.parent_org_id != null ? String(d.parent_org_id) : null;
			const pid = rawPid && validIds.has(rawPid) ? rawPid : String(root.id);
			add({ id: String(d.id), pid, name: d.name });
		}

		let hier: d3.HierarchyNode<TN>;
		try {
			hier = d3.stratify<TN>().id((n) => n.id).parentId((n) => n.pid)(rawNodes);
		} catch {
			return false;
		}

		const fullCount = hier.descendants().length;
		const hasChildren = new Set<string>();
		// eslint-disable-next-line @typescript-eslint/no-explicit-any
		hier.each((n: any) => { if (n.children?.length) hasChildren.add(n.data.id); });

		const searchAutoExpand = new Set<string>();
		if (q.length >= 2) {
			// eslint-disable-next-line @typescript-eslint/no-explicit-any
			hier.each((n: any) => {
				if (n.data.name.toLowerCase().includes(q)) {
					let p = n.parent;
					while (p) { searchAutoExpand.add(p.data.id); p = p.parent; }
				}
			});
		}

		// eslint-disable-next-line @typescript-eslint/no-explicit-any
		hier.each((n: any) => {
			if (n.depth < 2) return;
			if (expanded.has(n.data.id) || searchAutoExpand.has(n.data.id)) return;
			n.children = undefined;
		});
		const truncated = fullCount > hier.descendants().length;

		const W = container.clientWidth || 800;
		// Responsive height: use container height or clamp between 280–600px
		const H = Math.max(280, Math.min(container.clientHeight || 480, 600));
		const R = Math.min(W, H) / 2 - 60;

		const prevSvg = d3.select(container).select<SVGSVGElement>('svg').node();
		const savedTransform = prevSvg ? d3.zoomTransform(prevSvg) : null;
		const isFirstRender = !savedTransform;

		container.innerHTML = '';

		const svg = d3
			.select(container)
			.append('svg')
			.attr('width', W)
			.attr('height', H)
			.style('display', 'block')
			.style('cursor', 'grab')
			.style('background', '#1C2127'); // Palantir bg

		const g = svg.append('g');

		const zoom = d3
			.zoom<SVGSVGElement, unknown>()
			.scaleExtent([0.1, 4])
			.on('zoom', (e) => g.attr('transform', e.transform.toString()));
		// eslint-disable-next-line @typescript-eslint/no-explicit-any
		(svg as any).call(zoom);
		// eslint-disable-next-line @typescript-eslint/no-explicit-any
		(svg as any).call(zoom.transform, savedTransform ?? d3.zoomIdentity.translate(W / 2, H / 2));

		d3.tree<TN>().size([2 * Math.PI, R])(hier);

		// Palantir violet palette for dark background
		const palette = ['#ad99ff', '#9179f2', '#7961db', '#634DBF', '#4E3CA0'];
		const borderColor = '#394B59';

		// Links
		g.selectAll('path.link')
			.data(hier.links())
			.join('path')
			.attr('class', 'link')
			.attr('fill', 'none')
			.attr('stroke', borderColor)
			.attr('stroke-width', 1)
			// eslint-disable-next-line @typescript-eslint/no-explicit-any
			.attr('opacity', (d: any) => {
				if (!q) return 0.6;
				const srcMatch = d.source.data.name.toLowerCase().includes(q);
				const tgtMatch = d.target.data.name.toLowerCase().includes(q);
				return srcMatch || tgtMatch ? 0.8 : 0.08;
			})
			// eslint-disable-next-line @typescript-eslint/no-explicit-any
			.attr('d', (d3.linkRadial() as any).angle((d: any) => d.x).radius((d: any) => d.y));

		const nodeG = g
			.selectAll('g.node')
			.data(hier.descendants())
			.join('g')
			.attr('class', 'node')
			// eslint-disable-next-line @typescript-eslint/no-explicit-any
			.attr('transform', (d: any) =>
				`rotate(${(d.x * 180) / Math.PI - 90}) translate(${d.y}, 0)`
			)
			// eslint-disable-next-line @typescript-eslint/no-explicit-any
			.style('cursor', (d: any) => hasChildren.has(d.data.id) ? 'pointer' : 'default');

		// eslint-disable-next-line @typescript-eslint/no-explicit-any
		nodeG.on('click', (event: MouseEvent, d: any) => {
			if (!hasChildren.has(d.data.id)) return;
			const id = d.data.id;
			const next = new Set(expandedIds);
			if (next.has(id)) next.delete(id); else next.add(id);
			expandedIds = next;
			event.stopPropagation();
		});

		nodeG
			.append('circle')
			// eslint-disable-next-line @typescript-eslint/no-explicit-any
			.attr('r', (d: any) => (d.depth === 0 ? 7 : d.depth === 1 ? 5 : 3))
			// eslint-disable-next-line @typescript-eslint/no-explicit-any
			.attr('fill', (d: any) => {
				if (q && d.data.name.toLowerCase().includes(q)) return '#D9822B'; // gold highlight
				return palette[Math.min(d.depth, palette.length - 1)];
			})
			// eslint-disable-next-line @typescript-eslint/no-explicit-any
			.attr('opacity', (d: any) => (!q || d.data.name.toLowerCase().includes(q) ? 1 : 0.12))
			// eslint-disable-next-line @typescript-eslint/no-explicit-any
			.attr('stroke', (d: any) => {
				if (q && d.data.name.toLowerCase().includes(q)) return '#BF7326';
				if (!hasChildren.has(d.data.id)) return 'none';
				const isExp = expanded.has(d.data.id) || searchAutoExpand.has(d.data.id);
				return isExp ? '#ad99ff' : '#5C7080';
			})
			// eslint-disable-next-line @typescript-eslint/no-explicit-any
			.attr('stroke-dasharray', (d: any) => {
				if (!hasChildren.has(d.data.id)) return null;
				const isExp = expanded.has(d.data.id) || searchAutoExpand.has(d.data.id);
				return isExp ? null : '3,2';
			})
			// eslint-disable-next-line @typescript-eslint/no-explicit-any
			.attr('stroke-width', (d: any) => (hasChildren.has(d.data.id) ? 1.5 : 1));

		nodeG.append('title').text((d) => d.data.name);

		// Labels
		nodeG.each(function (d: any) {
			if (d.depth >= 2) return;
			const grp = d3.select(this);
			const label = d.depth === 0 ? d.data.name : shortName(d.data.name);
			const maxChars = d.depth === 0 ? 22 : 14;
			const lines = wrapLines(label, maxChars);
			const isLeft = d.x > Math.PI;
			const isRoot = d.depth === 0;
			const anchor = isRoot ? 'middle' : isLeft ? 'end' : 'start';
			const xOff = isRoot ? 0 : isLeft ? -10 : 10;
			const totalLines = lines.length;
			const matches = !q || d.data.name.toLowerCase().includes(q);

			const text = grp
				.append('text')
				// eslint-disable-next-line @typescript-eslint/no-explicit-any
				.attr('transform', !isRoot && isLeft ? 'rotate(180)' : (null as any))
				.attr('text-anchor', anchor)
				.attr('font-size', isRoot ? 11 : 9)
				.attr('fill', q && matches ? '#D9822B' : '#ABB3BF')
				.attr('font-weight', q && matches ? '600' : 'normal')
				.attr('opacity', matches ? 1 : 0.15);

			lines.forEach((line, i) => {
				text.append('tspan')
					.attr('x', xOff)
					.attr('dy', i === 0 ? `${-((totalLines - 1) * 1.1) / 2}em` : '1.1em')
					.text(line);
			});
		});

		if (isFirstRender) {
			requestAnimationFrame(() => {
				const bb = (g.node() as SVGGElement)?.getBBox();
				if (!bb || (bb.width === 0 && bb.height === 0)) return;
				const pad = 60;
				const sc = Math.min(
					bb.width > 0 ? (W - pad) / bb.width : 1,
					bb.height > 0 ? (H - pad) / bb.height : 1,
					1
				);
				const tx = W / 2 - (bb.x + bb.width / 2) * sc;
				const ty = H / 2 - (bb.y + bb.height / 2) * sc;
				// eslint-disable-next-line @typescript-eslint/no-explicit-any
				(svg as any).call(zoom.transform, d3.zoomIdentity.translate(tx, ty).scale(sc));
			});
		}

		return truncated;
	}

	// ── Sidebar helpers ───────────────────────────────────────────────────────
	let sidebarItems = $derived(query.trim() ? results : roots);
	let showMinHeader = $derived(!query.trim() && !loadingRoots);
</script>

<div class="flex-1 flex flex-col lg:flex-row min-h-0">

	<!-- ── Left sidebar ─────────────────────────────────────────────────────── -->
	<aside class="w-full lg:w-72 xl:w-80 shrink-0 flex flex-col"
	       style="background: var(--pt-bg-1); border-right: 1px solid var(--pt-border);">

		<!-- Search header -->
		<div class="p-4 flex-none" style="border-bottom: 1px solid var(--pt-border-muted);">
			<div class="flex items-center justify-between mb-3">
				<h1 class="pt-label">Organisation Explorer</h1>
				<!-- Mobile collapse toggle -->
				<button
					onclick={() => (sidebarCollapsed = !sidebarCollapsed)}
					class="lg:hidden flex items-center gap-1 text-xs px-2 py-1 transition-colors"
					style="color: var(--pt-text-muted); border: 1px solid var(--pt-border); border-radius: 2px;"
				>
					{sidebarCollapsed ? 'Show' : 'Hide'}
					<svg class="w-3 h-3 transition-transform {sidebarCollapsed ? 'rotate-180' : ''}"
					     fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" d="M4.5 15.75l7.5-7.5 7.5 7.5"/>
					</svg>
				</button>
			</div>
			<div class="relative">
				<svg class="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 pointer-events-none"
				     style="color: var(--pt-text-muted);" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z"/>
				</svg>
				<input
					type="text"
					placeholder="Search organisations…"
					bind:value={query}
					oninput={onInput}
					class="pt-input pl-8"
				/>
			</div>
		</div>

		<!-- Collapsible list body -->
		{#if !sidebarCollapsed}
			{#if showMinHeader}
				<div class="px-4 py-2 flex items-center justify-between flex-none"
				     style="background: var(--pt-bg-0); border-bottom: 1px solid var(--pt-border-muted);">
					<span class="pt-label">Ministries</span>
					{#if roots.length}
						<span class="text-xs" style="color: var(--pt-text-muted); font-family: var(--font-mono);">{roots.length}</span>
					{/if}
				</div>
			{/if}

			<div class="flex-1 overflow-y-auto lg:max-h-none" style="max-height: 40vh;">
				{#if (loadingRoots && !query) || searching}
					<div class="p-3 space-y-1">
						{#each Array(7) as _}
							<div class="h-10 rounded animate-pulse" style="background: var(--pt-bg-2);"></div>
						{/each}
					</div>
				{:else if searchError}
					<div class="p-4">
						<p class="text-sm" style="color: var(--pt-red);">{searchError}</p>
					</div>
				{:else if query && !results.length}
					<div class="p-8 text-center">
						<p class="text-sm" style="color: var(--pt-text-muted);">No results for "{query}"</p>
					</div>
				{:else}
					<ul class="py-1">
						{#each sidebarItems as org (org.id)}
							<li>
								<button
									onclick={() => selectOrg(org)}
									class="w-full text-left px-3 py-2.5 flex items-center gap-3 transition-colors"
									style={selected?.id === org.id
										? 'background: var(--pt-violet-tint); border-left: 2px solid var(--pt-violet); color: #ad99ff;'
										: 'color: var(--pt-text-secondary);'}
									onmouseover={(e) => {
										if (selected?.id !== org.id) (e.currentTarget as HTMLElement).style.background = 'var(--pt-bg-3)';
									}}
									onmouseout={(e) => {
										if (selected?.id !== org.id) (e.currentTarget as HTMLElement).style.background = '';
									}}
								>
									<div class="w-6 h-6 flex items-center justify-center shrink-0 transition-colors"
									     style="background: {selected?.id === org.id ? 'var(--pt-violet)' : 'var(--pt-bg-2)'}; border-radius: 2px;">
										<svg class="w-3 h-3"
										     style="color: {selected?.id === org.id ? '#fff' : 'var(--pt-text-muted)'};"
										     fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
											<path stroke-linecap="round" stroke-linejoin="round"
											      d="M3.75 21h16.5M4.5 3h15M5.25 3v18m13.5-18v18M9 6.75h1.5m-1.5 3h1.5m-1.5 3h1.5m3-6H15m-1.5 3H15m-1.5 3H15M9 21v-3.375c0-.621.504-1.125 1.125-1.125h3.75c.621 0 1.125.504 1.125 1.125V21"/>
										</svg>
									</div>
									<div class="min-w-0 flex-1">
										<p class="text-xs font-medium truncate leading-tight">
											{org.name}
										</p>
										{#if org.department}
											<p class="text-xs truncate mt-0.5" style="color: var(--pt-text-muted);">
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
		{/if}
	</aside>

	<!-- ── Right panel ──────────────────────────────────────────────────────── -->
	<section class="flex-1 overflow-y-auto" style="background: var(--pt-bg-0);">
		{#if !selected}
			<!-- Welcome state -->
			<div class="h-full flex items-center justify-center p-8 min-h-[50vh]">
				<div class="text-center max-w-xs">
					<div class="w-14 h-14 flex items-center justify-center mx-auto mb-4"
					     style="background: var(--pt-violet-tint); border: 1px solid var(--pt-border); border-radius: 2px;">
						<svg class="w-7 h-7" style="color: var(--pt-violet);" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round"
							      d="M2.25 21h19.5m-18-18v18m10.5-18v18m6-13.5V21M6.75 6.75h.75m-.75 3h.75m-.75 3h.75m3-6h.75m-.75 3h.75m-.75 3h.75M6.75 21v-3.375c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21M3 3h12m-.75 4.5H21"/>
						</svg>
					</div>
					<h2 class="text-sm font-semibold mb-1" style="color: var(--pt-text-primary);">Select a Ministry</h2>
					<p class="text-xs leading-relaxed" style="color: var(--pt-text-muted);">
						Choose a ministry from the sidebar or search to explore its hierarchy and track changes over time.
					</p>
				</div>
			</div>
		{:else}
			<div class="p-4 space-y-3 max-w-5xl mx-auto">

				<!-- Org header -->
				<div class="pt-card">
					<div class="flex items-center gap-3">
						<div class="w-9 h-9 flex items-center justify-center shrink-0"
						     style="background: var(--pt-violet); border-radius: 2px;">
							<svg class="w-4.5 h-4.5 text-white" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round"
								      d="M3.75 21h16.5M4.5 3h15M5.25 3v18m13.5-18v18M9 6.75h1.5m-1.5 3h1.5m-1.5 3h1.5m3-6H15m-1.5 3H15m-1.5 3H15M9 21v-3.375c0-.621.504-1.125 1.125-1.125h3.75c.621 0 1.125.504 1.125 1.125V21"/>
							</svg>
						</div>
						<div class="min-w-0 flex-1">
							<h2 class="text-sm font-semibold leading-snug" style="color: var(--pt-text-primary);">
								{selected.name}
							</h2>
							{#if selected.department}
								<p class="text-xs mt-0.5" style="color: var(--pt-text-muted);">{selected.department}</p>
							{/if}
						</div>
						{#if selectedDate}
							<span class="pt-tag pt-tag-violet shrink-0">{fmt(selectedDate)}</span>
						{/if}
					</div>
				</div>

				<!-- Stats cards — responsive grid -->
				<div class="grid grid-cols-1 sm:grid-cols-3 gap-2">
					<!-- Sub-agencies -->
					<div class="pt-card">
						{#if loadingTree}
							<div class="h-7 w-14 rounded animate-pulse mb-1" style="background: var(--pt-bg-3);"></div>
						{:else}
							<div class="text-xl font-bold pt-data" style="color: #ad99ff;">{metrics.total.toLocaleString()}</div>
						{/if}
						<div class="text-xs font-medium mt-1" style="color: var(--pt-text-secondary);">Sub-agencies</div>
						<div class="text-xs mt-0.5" style="color: var(--pt-text-muted);">Total units</div>
					</div>

					<!-- Hierarchy depth -->
					<div class="pt-card">
						{#if loadingTree}
							<div class="h-7 w-10 rounded animate-pulse mb-1" style="background: var(--pt-bg-3);"></div>
						{:else}
							<div class="text-xl font-bold pt-data" style="color: #68b9e5;">{metrics.depth}</div>
						{/if}
						<div class="text-xs font-medium mt-1" style="color: var(--pt-text-secondary);">Hierarchy depth</div>
						<div class="text-xs mt-0.5" style="color: var(--pt-text-muted);">Levels below root</div>
					</div>

					<!-- Employees at snapshot -->
					<div class="pt-card">
						{#if loadingHeadcount}
							<div class="h-7 w-12 rounded animate-pulse mb-1" style="background: var(--pt-bg-3);"></div>
						{:else}
							<div class="text-xl font-bold pt-data" style="color: #3dcc91;">
								{headcount !== null ? headcount.toLocaleString() : '—'}
							</div>
						{/if}
						<div class="text-xs font-medium mt-1" style="color: var(--pt-text-secondary);">Employees</div>
						<div class="text-xs mt-0.5" style="color: var(--pt-text-muted);">
							At {selectedDate ? fmt(selectedDate) : 'snapshot'}
						</div>
					</div>
				</div>

				<!-- D3 hierarchy map -->
				<div class="pt-card" style="padding: 0; overflow: hidden;">
					<div class="px-4 py-2.5 flex items-center justify-between gap-3 flex-none"
					     style="border-bottom: 1px solid var(--pt-border-muted);">
						<div class="flex items-center gap-2 min-w-0">
							<h3 class="text-xs font-semibold" style="color: var(--pt-text-primary);">Hierarchy Map</h3>
							<span class="text-xs hidden sm:inline" style="color: var(--pt-text-muted);">
								click node to expand · scroll to zoom · drag to pan
							</span>
						</div>
						<div class="flex items-center gap-2 shrink-0">
							{#if vizTruncated}
								<span class="pt-tag pt-tag-orange hidden md:inline-flex">
									2 levels of {metrics.total + 1}
								</span>
							{/if}
							{#if tree.length}
								<div class="relative">
									<svg class="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 pointer-events-none"
									     style="color: var(--pt-text-muted);"
									     fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round"
										      d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z"/>
									</svg>
									<input
										type="text"
										bind:value={vizSearch}
										placeholder="Highlight agency…"
										class="text-xs pl-7 pr-6 py-1.5 w-32"
										style="background: var(--pt-bg-0); border: 1px solid var(--pt-border); border-radius: 2px;
										       color: var(--pt-text-primary); outline: none;"
									/>
									{#if vizSearch}
										<button
											onclick={() => (vizSearch = '')}
											class="absolute right-1.5 top-1/2 -translate-y-1/2 text-sm leading-none px-0.5"
											style="color: var(--pt-text-muted);"
											aria-label="Clear"
										>×</button>
									{/if}
								</div>
							{/if}
						</div>
					</div>
					<!-- Responsive viz container: clamp height for mobile -->
					<div class="relative w-full" style="height: clamp(280px, 50vh, 580px);">
						{#if loadingTree}
							<div class="absolute inset-0 flex items-center justify-center" style="background: #1C2127;">
								<div class="flex flex-col items-center gap-3">
									<div class="w-7 h-7 border-2 rounded-full animate-spin"
									     style="border-color: var(--pt-violet); border-top-color: transparent;"></div>
									<p class="text-xs" style="color: var(--pt-text-muted);">Loading hierarchy…</p>
								</div>
							</div>
						{:else if !tree.length}
							<div class="absolute inset-0 flex items-center justify-center">
								<p class="text-xs" style="color: var(--pt-text-muted);">
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
					<div class="pt-card">
						<div class="flex items-center justify-between mb-4">
							<div>
								<span class="pt-label">Snapshot</span>
								{#if loadingTree}
									<div class="h-5 w-24 rounded animate-pulse mt-1" style="background: var(--pt-bg-3);"></div>
								{:else}
									<p class="text-base font-bold mt-0.5 leading-none pt-data" style="color: #ad99ff;">{fmt(selectedDate)}</p>
								{/if}
							</div>
							<span class="text-xs tabular-nums pt-data px-2 py-1"
							      style="color: var(--pt-text-muted); background: var(--pt-bg-2); border-radius: 2px;">
								{sliderIdx + 1} / {timeline.length}
							</span>
						</div>

						<div class="relative px-1">
							<input
								type="range"
								min="0"
								max={timeline.length - 1}
								step="1"
								bind:value={sliderIdx}
								oninput={onSliderInput}
								class="w-full h-2 rounded-none appearance-none cursor-pointer"
								style="accent-color: var(--pt-violet);"
							/>
						</div>

						<div class="relative mt-3 h-6 px-1">
							{#each yearTicks as tick}
								<div class="absolute flex flex-col items-center"
								     style="left: {tick.pct}%; transform: translateX(-50%)">
									<div class="w-px h-2" style="background: var(--pt-border);"></div>
									<span class="text-xs mt-0.5 tabular-nums pt-data" style="color: var(--pt-text-muted);">
										{tick.year}
									</span>
								</div>
							{/each}
						</div>
					</div>
				{/if}

			</div>
		{/if}
	</section>
</div>
