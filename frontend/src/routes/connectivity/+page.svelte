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
	const orgCache     = new Map<number, OrgResult>();

	async function fetchRootMinistry(orgId: number): Promise<OrgResult | null> {
		if (rootOrgCache.has(orgId)) return rootOrgCache.get(orgId)!;
		try {
			const root = await organisations.root(orgId);
			rootOrgCache.set(orgId, root);
			return root;
		} catch { return null; }
	}

	async function fetchOrg(orgId: number): Promise<OrgResult | null> {
		if (orgCache.has(orgId)) return orgCache.get(orgId)!;
		try {
			const org = await organisations.get(orgId);
			orgCache.set(orgId, org);
			return org;
		} catch { return null; }
	}

	// Node positions persisted across D3 re-renders so ministry update is stable
	const nodePositions = new Map<string, { x: number; y: number }>();

	// Edge year-range cache: edgeKey → yearLabel
	const edgeYearCache = new Map<string, string>();

	// ---------------------------------------------------------------------------
	// Person slot
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
		ministryColorMap.clear(); nextPaletteIdx = 0;
		nodePositions.clear(); edgeYearCache.clear(); orgCache.clear();
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
		/** Immediate agency name when this org node is NOT a ministry root */
		agencyName?: string;
		/** True when this org node IS the root (ministry-level) */
		isMinistry?: boolean;
		/** Most recent role/rank (person nodes) */
		role?: string;
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
		/** "YYYY–YYYY" annotation shown on path edges */
		yearLabel?: string;
	}

	let graphNodes  = $state<GNode[]>([]);
	let graphEdges  = $state<GEdge[]>([]);
	let pathResult  = $state<{ nodes: PathNode[]; length: number } | null>(null);
	let pathError   = $state('');
	let pathLoading = $state(false);
	let temporal    = $state(true);

	// Hover tooltip
	let hoveredNode  = $state<GNode | null>(null);
	let hoverClientX = $state(0);
	let hoverClientY = $state(0);

	// ---------------------------------------------------------------------------
	// Helpers
	// ---------------------------------------------------------------------------
	function edgeEndpointId(ep: string | GNode): string {
		return typeof ep === 'string' ? ep : ep.id;
	}

	function latestRole(profile?: EmploymentEntry[]): string | null {
		if (!profile?.length) return null;
		const sorted = [...profile].sort((a, b) => {
			if (!a.start_date) return 1; if (!b.start_date) return -1;
			return b.start_date.localeCompare(a.start_date);
		});
		return sorted[0].rank ?? null;
	}

	function yearRangeLabel(entry?: EmploymentEntry): string | undefined {
		if (!entry?.start_date) return undefined;
		const start = entry.start_date.slice(0, 4);
		const end   = entry.end_date?.slice(0, 4) ?? 'now';
		return `${start}–${end}`;
	}

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
			role: n.node_type === 'person' ? (latestRole(n.employment_profile) ?? undefined) : undefined,
			inPath: true,
			isSource: n.person_id === sourceId,
			isTarget: n.person_id === targetId,
			expanded: false
		} satisfies GNode));

		graphEdges = nodes.slice(0, -1).map((n, i) => {
			const next = nodes[i + 1];
			let yearLabel: string | undefined;

			if (n.node_type === 'person' && next.node_type === 'organization') {
				const entry = n.employment_profile?.find(e => e.org_id === next.org_id);
				yearLabel = yearRangeLabel(entry);
			} else if (n.node_type === 'organization' && next.node_type === 'person') {
				const entry = next.employment_profile?.find(e => e.org_id === n.org_id);
				yearLabel = yearRangeLabel(entry);
			}

			return { source: n.node_id, target: next.node_id, inPath: true, yearLabel };
		});
	}

	/** Async: resolve root ministry for all org nodes, then patch graphNodes */
	async function resolveMinistries() {
		const orgNodes = graphNodes.filter(n => n.type === 'org' && n.org_id != null);
		if (!orgNodes.length) return;

		const resolved = await Promise.all(
			orgNodes.map(async n => {
				// Placeholder names ("Org 12345") come from expandNode — resolve the real name.
				const isPlaceholder = /^Org \d+$/.test(n.name);
				const [root, actual] = await Promise.all([
					fetchRootMinistry(n.org_id!),
					isPlaceholder ? fetchOrg(n.org_id!) : Promise.resolve(null)
				]);
				const orgName  = actual?.name ?? n.name;
				const rootName = root?.name ?? orgName;
				return { id: n.id, orgName, rootName };
			})
		);

		for (const r of resolved) getMinistryColor(r.rootName);

		const patchMap = new Map(resolved.map(r => [r.id, r]));

		graphNodes = graphNodes.map(n => {
			if (patchMap.has(n.id)) {
				const { orgName, rootName } = patchMap.get(n.id)!;
				const isMinistry = orgName === rootName;
				return {
					...n,
					ministry:    rootName,
					agencyName:  isMinistry ? undefined : orgName,
					isMinistry
				};
			}
			// Propagate ministry to adjacent person nodes
			if (n.type === 'person') {
				for (const e of graphEdges) {
					const s = edgeEndpointId(e.source);
					const t = edgeEndpointId(e.target);
					if (s === n.id && patchMap.has(t)) return { ...n, ministry: patchMap.get(t)!.rootName };
					if (t === n.id && patchMap.has(s)) return { ...n, ministry: patchMap.get(s)!.rootName };
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
		const anchor = nodePositions.get(node.id) ?? { x: 0, y: 0 };

		for (const colleague of deg1) {
			const pId = `person_${colleague.id}`;
			if (!existingIds.has(pId)) {
				toAddNodes.push({
					id: pId, type: 'person', name: colleague.name,
					person_id: colleague.id, inPath: false,
					isSource: false, isTarget: false, expanded: false,
					x: anchor.x + (Math.random() - 0.5) * 80,
					y: anchor.y + (Math.random() - 0.5) * 80
				});
				existingIds.add(pId);
			}
			for (const orgId of colleague.shared_organizations) {
				const oId = `org_${orgId}`;
				if (!existingIds.has(oId)) {
					toAddNodes.push({
						id: oId, type: 'org', name: `Org ${orgId}`, org_id: orgId,
						inPath: false, isSource: false, isTarget: false, expanded: false,
						x: anchor.x + (Math.random() - 0.5) * 100,
						y: anchor.y + (Math.random() - 0.5) * 100
					});
					existingIds.add(oId);
				}
				const edgeExists = (a: string, b: string) =>
					graphEdges.some(e => {
						const s = edgeEndpointId(e.source); const t = edgeEndpointId(e.target);
						return (s === a && t === b) || (s === b && t === a);
					});
				if (!edgeExists(node.id, oId)) toAddEdges.push({ source: node.id, target: oId, inPath: false });
				if (!edgeExists(pId,     oId)) toAddEdges.push({ source: pId,     target: oId, inPath: false });
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
		document.body.style.overflow = 'hidden';
		// Seed dimensions immediately so first renderD3() uses real canvas size
		if (svgEl) {
			const r = svgEl.getBoundingClientRect();
			if (r.width > 0)  svgWidth  = r.width;
			if (r.height > 0) svgHeight = r.height;
		}
		const ro = new ResizeObserver(entries => {
			for (const e of entries) {
				if (e.contentRect.width  > 0) svgWidth  = e.contentRect.width;
				if (e.contentRect.height > 0) svgHeight = e.contentRect.height;
			}
		});
		if (svgEl) ro.observe(svgEl);
		return () => { document.body.style.overflow = ''; ro.disconnect(); };
	});

	$effect(() => {
		if (!svgEl || graphNodes.length === 0) return;
		// Access dimensions to re-render when canvas resizes
		void svgWidth; void svgHeight;
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

	function orgFill(d: GNode): string {
		return d.ministry ? getMinistryColor(d.ministry) : (d.inPath ? '#6366f1' : '#94a3b8');
	}

	function renderD3() {
		if (!svgEl) return;
		// Stop any in-progress simulation before re-rendering to avoid tick race
		simulation?.stop();

		// Read actual dimensions into LOCAL variables — never mutate reactive state
		// here or the $effect will re-trigger in a loop.
		const rect = svgEl.getBoundingClientRect();
		const W = rect.width  > 0 ? rect.width  : svgWidth;
		const H = rect.height > 0 ? rect.height : svgHeight;

		const svg = d3.select(svgEl);
		svg.selectAll('*').remove();

		// Defs: drop shadow
		const defs = svg.append('defs');
		const shadow = defs.append('filter')
			.attr('id', 'node-shadow').attr('x', '-20%').attr('y', '-20%').attr('width', '140%').attr('height', '140%');
		shadow.append('feDropShadow').attr('dx', 0).attr('dy', 1).attr('stdDeviation', 2).attr('flood-opacity', 0.18);

		const g = svg.append('g');

		const zoomBehavior = d3.zoom<SVGSVGElement, unknown>()
			.scaleExtent([0.15, 5])
			.on('zoom', e => g.attr('transform', e.transform));
		svg.call(zoomBehavior);

		// Deep-copy with stored positions
		const simNodes: GNode[] = graphNodes.map(n => ({
			...n,
			x: nodePositions.get(n.id)?.x,
			y: nodePositions.get(n.id)?.y
		}));
		const simEdges: GEdge[] = graphEdges.map(e => ({
			source: edgeEndpointId(e.source),
			target: edgeEndpointId(e.target),
			inPath: e.inPath,
			yearLabel: e.yearLabel
		}));

		const hasPositions = simNodes.some(n => n.x != null);

		// Pre-position path nodes in a horizontal sequence (reduces crossings on first render)
		const pathNodeIds = simNodes.filter(n => n.inPath).map(n => n.id);
		const totalPath   = pathNodeIds.length;
		if (!hasPositions && totalPath > 1) {
			const margin = W * 0.1;
			const span   = W - 2 * margin;
			simNodes.forEach(n => {
				const idx = pathNodeIds.indexOf(n.id);
				if (idx !== -1) {
					n.x = margin + (idx / (totalPath - 1)) * span;
					n.y = H / 2 + (idx % 2 === 0 ? -20 : 20);
				}
			});
		}

		simulation = d3.forceSimulation<GNode>(simNodes)
			.alpha(hasPositions ? 0.15 : 0.8)
			.force('link',    d3.forceLink<GNode, GEdge>(simEdges).id(d => d.id).distance(d => d.inPath ? 160 : 100))
			.force('charge',  d3.forceManyBody().strength(-700))
			.force('center',  d3.forceCenter(W / 2, H / 2).strength(0.25))
			.force('collide', d3.forceCollide<GNode>(d => nodeRadius(d) + 22))
			// Gentle left-to-right ordering for path nodes to suppress crossings
			.force('path-x',  d3.forceX<GNode>(d => {
				const idx = pathNodeIds.indexOf(d.id);
				if (idx === -1) return W / 2;
				const margin = W * 0.12;
				return margin + (idx / Math.max(totalPath - 1, 1)) * (W - 2 * margin);
			}).strength(d => d.inPath ? 0.35 : 0.02))
			.force('path-y',  d3.forceY<GNode>(H / 2).strength(d => d.inPath ? 0.3 : 0.08))
			.force('y-center', d3.forceY<GNode>(H / 2).strength(0.04));

		// ── Links ──────────────────────────────────────────
		const link = g.append('g').attr('class', 'links')
			.selectAll<SVGLineElement, GEdge>('line')
			.data(simEdges)
			.join('line')
			.attr('stroke',          d => d.inPath ? '#818cf8' : '#cbd5e1')
			.attr('stroke-width',    d => d.inPath ? 2.5 : 1.2)
			.attr('stroke-dasharray',d => { if (!d.inPath) return '5,4'; return d.yearLabel ? null : '4,3'; })
			.attr('opacity',         d => d.inPath ? 1 : 0.45);

		// ── Edge year labels ───────────────────────────────
		const edgeLabel = g.append('g').attr('class', 'edge-labels')
			.selectAll<SVGTextElement, GEdge>('text')
			.data(simEdges.filter(e => e.yearLabel))
			.join('text')
			.attr('text-anchor', 'middle')
			.attr('font-size', '16px')
			.attr('font-weight', '600')
			.attr('fill', '#a5b4fc')
			// Dark halo for readability over the dark background
			.style('paint-order', 'stroke')
			.attr('stroke', '#1C2127')
			.attr('stroke-width', 4)
			.attr('stroke-linejoin', 'round')
			.attr('pointer-events', 'none')
			.text(d => d.yearLabel!);

		// ── Node groups ────────────────────────────────────
		const drag = d3.drag<SVGGElement, GNode>()
			.on('start', (event, d) => { if (!event.active) simulation?.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
			.on('drag',  (event, d) => { d.fx = event.x; d.fy = event.y; })
			.on('end',   (event, d) => { if (!event.active) simulation?.alphaTarget(0); d.fx = null; d.fy = null; });

		const node = g.append('g').attr('class', 'nodes')
			.selectAll<SVGGElement, GNode>('g')
			.data(simNodes)
			.join('g')
			.style('cursor', d => d.type === 'person' ? 'pointer' : 'grab')
			.call(drag)
			.on('click', (_e, d) => { if (d.type === 'person') openModal(d); })
			.on('mouseover', (event, d) => {
				hoveredNode  = { ...d };
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

		// Outer accent ring (source = solid, target = dashed)
		personNodes.filter(d => d.isSource || d.isTarget)
			.append('circle')
			.attr('r',              d => nodeRadius(d) + 6)
			.attr('fill',           'none')
			.attr('stroke',         d => d.isSource ? '#2563eb' : '#059669')
			.attr('stroke-width',   2.5)
			.attr('stroke-dasharray', d => d.isSource ? null : '6,3')
			.attr('opacity',        0.5);

		personNodes.append('circle')
			.attr('r',            nodeRadius)
			.attr('fill',         personFill)
			.attr('stroke',       d => d.expanded ? '#fbbf24' : 'white')
			.attr('stroke-width', d => d.expanded ? 3 : 2)
			.attr('filter',       'url(#node-shadow)');

		personNodes.append('text')
			.attr('text-anchor', 'middle').attr('dominant-baseline', 'central')
			.attr('fill', 'white').attr('font-size', '17px').attr('font-weight', '700')
			.attr('letter-spacing', '0.5px').attr('pointer-events', 'none')
			.text(d => d.name.slice(0, 2).toUpperCase());

		// ── Org shapes — diamond for ministry, rect for agency ──
		const orgNodes = node.filter(d => d.type === 'org');

		// Ministry: diamond (◆)
		orgNodes.filter(d => !!d.isMinistry)
			.append('polygon')
			.attr('points', '0,-22 36,0 0,22 -36,0')
			.attr('fill',         orgFill)
			.attr('stroke',       'white')
			.attr('stroke-width', 1.5)
			.attr('filter',       'url(#node-shadow)');

		// Agency: rounded rect
		orgNodes.filter(d => !d.isMinistry)
			.append('rect')
			.attr('x', -36).attr('y', -15).attr('width', 72).attr('height', 30).attr('rx', 8)
			.attr('fill',         orgFill)
			.attr('stroke',       'white')
			.attr('stroke-width', 1.5)
			.attr('filter',       'url(#node-shadow)');

		// ── Label inside org shape — short identifier ─────────
		orgNodes.append('text')
			.attr('text-anchor', 'middle').attr('dominant-baseline', 'central')
			.attr('fill', 'white').attr('font-size', '10px').attr('font-weight', '600')
			.attr('pointer-events', 'none')
			.text(d => truncate(d.agencyName ?? d.ministry ?? d.name, 13));

		// ── Name labels below nodes ─────────────────────────
		// Person nodes: single line (name only)
		personNodes.append('text')
			.attr('text-anchor', 'middle')
			.attr('y', d => nodeRadius(d) + 20)
			.attr('fill', '#d3dce6').attr('font-size', '17px')
			.attr('font-weight', d => (d.isSource || d.isTarget) ? '700' : '500')
			.style('paint-order', 'stroke')
			.attr('stroke', '#1C2127').attr('stroke-width', 3).attr('stroke-linejoin', 'round')
			.attr('pointer-events', 'none')
			.text(d => truncate(d.name, 24));

		// Org nodes: 2-line (org name + ministry in smaller text for agencies)
		orgNodes.each(function(d) {
			const yBase = d.isMinistry ? 35 : 30;
			const text = d3.select<SVGGElement, GNode>(this).append('text')
				.attr('text-anchor', 'middle')
				.attr('pointer-events', 'none')
				.style('paint-order', 'stroke')
				.attr('stroke', '#1C2127').attr('stroke-width', 3).attr('stroke-linejoin', 'round');
			text.append('tspan')
				.attr('x', 0).attr('y', yBase)
				.attr('fill', '#d3dce6').attr('font-size', '16px').attr('font-weight', '500')
				.text(truncate(d.agencyName ?? d.name, 22));
			if (d.agencyName && d.ministry) {
				text.append('tspan')
					.attr('x', 0).attr('dy', '1.3em')
					.attr('fill', getMinistryColor(d.ministry))
					.attr('font-size', '13px').attr('font-weight', '600')
					.text(truncate(d.ministry, 22));
			}
		});

		// Source / Target label
		personNodes.filter(d => d.isSource || d.isTarget)
			.append('text')
			.attr('text-anchor', 'middle')
			.attr('y', d => nodeRadius(d) + 38)
			.attr('fill', d => d.isSource ? '#68b9e5' : '#3dcc91')
			.attr('font-size', '16px').attr('font-weight', '700').attr('letter-spacing', '0.5px')
			.attr('pointer-events', 'none')
			.text(d => d.isSource ? '▲ SOURCE' : '▼ TARGET');

		// ── Tick ───────────────────────────────────────────
		simulation.on('tick', () => {
			simNodes.forEach(n => {
				if (n.x != null && n.y != null) nodePositions.set(n.id, { x: n.x, y: n.y });
			});
			link
				.attr('x1', d => (d.source as GNode).x ?? 0).attr('y1', d => (d.source as GNode).y ?? 0)
				.attr('x2', d => (d.target as GNode).x ?? 0).attr('y2', d => (d.target as GNode).y ?? 0);
			edgeLabel
				.attr('x', d => (((d.source as GNode).x ?? 0) + ((d.target as GNode).x ?? 0)) / 2)
				.attr('y', d => (((d.source as GNode).y ?? 0) + ((d.target as GNode).y ?? 0)) / 2 - 7);
			node.attr('transform', d => `translate(${d.x ?? 0},${d.y ?? 0})`);
		});

		// ── Fit to view after simulation settles ───────────
		simulation.on('end', () => {
			const pad = 80; // px padding around all nodes
			const xs = simNodes.map(n => n.x ?? W / 2);
			const ys = simNodes.map(n => n.y ?? H / 2);
			const x0 = Math.min(...xs) - pad;
			const x1 = Math.max(...xs) + pad;
			const y0 = Math.min(...ys) - pad;
			const y1 = Math.max(...ys) + pad;
			const contentW = x1 - x0;
			const contentH = y1 - y0;
			// Cap scale at 1.8× so we don't zoom in too aggressively on small graphs
			const scale = Math.min(W / contentW, H / contentH, 1.8);
			const tx = (W - scale * (x0 + x1)) / 2;
			const ty = (H - scale * (y0 + y1)) / 2;
			svg.transition().duration(600)
				.call(zoomBehavior.transform, d3.zoomIdentity.translate(tx, ty).scale(scale));
		});
	}

	// ---------------------------------------------------------------------------
	// Stats modal
	// ---------------------------------------------------------------------------
	let modalNode      = $state<GNode | null>(null);
	let modalNetwork   = $state<ColleagueNetwork | null>(null);
	let modalLoading   = $state(false);
	let ministryCounts = $state<{ ministry: string; count: number }[]>([]);

	async function openModal(node: GNode) {
		modalNode = node; modalNetwork = null; ministryCounts = []; modalLoading = true;
		try {
			if (!node.person_id) return;
			const net = await fetchPersonNetwork(node.person_id);
			modalNetwork = net;
			const deg1   = net.colleagues_by_degree['1'] ?? [];
			const orgIds = [...new Set(deg1.flatMap(c => c.shared_organizations))];
			const roots  = await Promise.all(orgIds.map(id => fetchRootMinistry(id)));
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

	const connectionStats = $derived({
		ministries: new Set(graphNodes.filter(n => n.inPath && n.ministry).map(n => n.ministry)).size,
		agencies:   graphNodes.filter(n => n.inPath && n.type === 'org').length
	});

	const overlapTimeline = $derived((() => {
		const pathEdges = graphEdges.filter(e => e.inPath && e.yearLabel);
		if (!pathEdges.length) return null;
		const years: number[] = [];
		for (const e of pathEdges) {
			const parts = e.yearLabel!.split('–');
			const start = parseInt(parts[0]);
			if (!isNaN(start)) years.push(start);
			if (parts[1] && parts[1] !== 'now') {
				const end = parseInt(parts[1]);
				if (!isNaN(end)) years.push(end);
			}
		}
		if (!years.length) return null;
		const min = Math.min(...years);
		const max = Math.max(...years);
		return min === max ? String(min) : `${min}–${max}`;
	})());

	function collapseExpanded() {
		graphNodes = graphNodes.filter(n => n.inPath).map(n => ({ ...n, expanded: false }));
		graphEdges = graphEdges.filter(e => e.inPath);
	}

	let expandingAll = $state(false);
	async function expandAllNodes() {
		if (expandingAll) return;
		expandingAll = true;
		try {
			const toExpand = graphNodes.filter(n => n.inPath && n.type === 'person' && !n.expanded);
			await Promise.all(toExpand.map(n => expandNode(n)));
		} finally { expandingAll = false; }
	}

	function resetGraph() {
		if (pathResult?.nodes.length) {
			// Restore the original path layout
			nodePositions.clear();
			edgeYearCache.clear();
			buildGraphFromPath(pathResult.nodes);
			resolveMinistries();
		} else {
			pathResult = null; pathError = ''; graphNodes = []; graphEdges = [];
			nodePositions.clear(); edgeYearCache.clear();
		}
	}
</script>

<div class="flex-1 flex flex-col min-h-0">

	<!-- ── Row 1: Title + controls bar ───────────────────── -->
	<div class="flex-none px-4 py-2.5 flex items-center justify-between gap-3 flex-wrap"
	     style="background: var(--pt-bg-1); border-bottom: 1px solid var(--pt-border);">
		<div class="flex items-center gap-2 min-w-0">
			<h1 class="text-sm font-semibold tracking-widest uppercase" style="color: var(--pt-text-primary);">Connectivity Explorer</h1>
			<InfoTip tip="Find the shortest connection path between two people through shared organisations. Click any person node to view their network stats." />
		</div>
		<div class="flex items-center gap-3 flex-wrap">
			<div class="flex items-center gap-1.5">
				<ConfidenceSlider bind:value={confidenceThreshold} compact={true} />
				<InfoTip tip="Variants below this score land in &quot;Not in timeline&quot; by default." />
			</div>
			<label class="flex items-center gap-1.5 cursor-pointer shrink-0">
				<input type="checkbox" bind:checked={temporal}
					onchange={() => { if (source.selected && target.selected) findPath(); }}
					style="accent-color: var(--pt-blue); width: 14px; height: 14px;"/>
				<span class="text-sm" style="color: var(--pt-text-secondary);">Temporal</span>
				<InfoTip tip="Only finds connections where people were physically working together at the same time." />
			</label>
			{#if source.selected && target.selected}
				<button onclick={findPath} disabled={pathLoading} class="pt-button pt-button-primary">
					{pathLoading ? 'Searching…' : 'Find Connection'}
				</button>
			{/if}
		</div>
	</div>

	<!-- ── Row 2: Source + Target search ────────────────── -->
	<div class="flex-none" style="background: var(--pt-bg-1); border-bottom: 1px solid var(--pt-border);">
		<div class="grid grid-cols-1 md:grid-cols-2" style="divide-color: var(--pt-border);">

			<!-- Source slot -->
			<div class="p-4 space-y-3 overflow-y-auto md:max-h-[30vh] max-h-[35vh]"
			     style="border-bottom: 1px solid var(--pt-border-muted);">
				<div class="flex items-center gap-1.5">
					<!-- Blueprint blue source indicator -->
					<span class="w-2 h-2 shrink-0" style="background: var(--pt-blue); border-radius: 50%;"></span>
					<p class="pt-label" style="color: #68b9e5;">Source</p>
					<InfoTip tip="The person you're tracing FROM. Drag variants between zones to fine-tune which name spellings are included." />
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
						careerData={source.career}
						ontoggle={(name) => toggleVariant(source, name)}
					/>
				{/if}
			</div>

			<!-- Target slot -->
			<div class="p-4 space-y-3 overflow-y-auto md:max-h-[30vh] max-h-[35vh]">
				<div class="flex items-center gap-1.5">
					<span class="w-2 h-2 shrink-0" style="border: 2px dashed var(--pt-green); border-radius: 50%;"></span>
					<p class="pt-label" style="color: #3dcc91;">Target</p>
					<InfoTip tip="The person you're tracing TO. The graph shows the shortest path between Source and Target through shared organisations." />
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
						careerData={target.career}
						ontoggle={(name) => toggleVariant(target, name)}
					/>
				{/if}
			</div>
		</div>
	</div>

	<!-- ── Row 3: Status / results toolbar (flex-none, no graph overlap) ── -->
	{#if pathLoading}
		<div class="flex-none px-4 py-2 flex items-center gap-2"
		     style="background: var(--pt-bg-1); border-bottom: 1px solid var(--pt-border);">
			<div class="w-3 h-3 rounded-full animate-pulse" style="background: var(--pt-blue);"></div>
			<span class="text-sm" style="color: var(--pt-text-muted);">Searching for connection…</span>
		</div>
	{:else if pathError}
		<div class="flex-none px-4 py-2 text-sm"
		     style="background: var(--pt-red-tint); border-bottom: 1px solid var(--pt-red); color: #ff7373;">
			{pathError}
		</div>
	{:else if pathResult && pathResult.nodes.length === 0}
		<div class="flex-none px-4 py-2 text-sm"
		     style="background: var(--pt-orange-tint); border-bottom: 1px solid var(--pt-orange); color: #ffb366;">
			No connection found — try disabling Temporal mode
		</div>
	{:else if pathResult && pathResult.nodes.length > 0}
		<!-- ── Stat cards + graph controls ─────────────────── -->
		<div class="flex-none px-3 py-2 flex items-center justify-between gap-3 flex-wrap"
		     style="background: var(--pt-bg-0); border-bottom: 1px solid var(--pt-border-muted);">
			<!-- Stat cards row -->
			<div class="flex items-stretch gap-1.5 overflow-x-auto" style="scrollbar-width: none;">
				<!-- Degrees -->
				<div class="flex flex-col items-center justify-center px-3 py-1.5 shrink-0"
				     style="background: var(--pt-bg-1); border: 1px solid var(--pt-border-muted); border-radius: 2px; min-width: 60px;">
					<span class="text-base font-bold tabular-nums pt-data leading-none" style="color: #ad99ff;">{degreeBadge}</span>
					<span class="pt-label mt-0.5" style="font-size: 0.65rem;">{degreeBadge === 1 ? 'Degree' : 'Degrees'}</span>
				</div>
				{#if connectionStats.ministries > 0}
				<div class="flex flex-col items-center justify-center px-3 py-1.5 shrink-0"
				     style="background: var(--pt-bg-1); border: 1px solid var(--pt-border-muted); border-radius: 2px; min-width: 60px;">
					<span class="text-base font-bold tabular-nums pt-data leading-none" style="color: var(--pt-text-primary);">{connectionStats.ministries}</span>
					<span class="pt-label mt-0.5" style="font-size: 0.65rem;">{connectionStats.ministries === 1 ? 'Ministry' : 'Ministries'}</span>
				</div>
				{/if}
				{#if connectionStats.agencies > 0}
				<div class="flex flex-col items-center justify-center px-3 py-1.5 shrink-0"
				     style="background: var(--pt-bg-1); border: 1px solid var(--pt-border-muted); border-radius: 2px; min-width: 60px;">
					<span class="text-base font-bold tabular-nums pt-data leading-none" style="color: var(--pt-text-primary);">{connectionStats.agencies}</span>
					<span class="pt-label mt-0.5" style="font-size: 0.65rem;">{connectionStats.agencies === 1 ? 'Agency' : 'Agencies'}</span>
				</div>
				{/if}
				{#if overlapTimeline}
				<div class="flex flex-col items-center justify-center px-3 py-1.5 shrink-0"
				     style="background: var(--pt-bg-1); border: 1px solid var(--pt-border-muted); border-radius: 2px; min-width: 60px;">
					<span class="text-base font-bold tabular-nums pt-data leading-none" style="color: var(--pt-text-primary);">{overlapTimeline}</span>
					<span class="pt-label mt-0.5" style="font-size: 0.65rem;">Timeline</span>
				</div>
				{/if}
			</div>
			<!-- Graph controls -->
			<div class="flex gap-1.5 shrink-0">
				<button onclick={resetGraph} class="pt-button pt-button-outlined">↺ Reset</button>
				<button onclick={expandAllNodes} disabled={expandingAll} class="pt-button pt-button-outlined disabled:opacity-50 disabled:cursor-not-allowed">
					{expandingAll ? '⏳ Expanding…' : '⊕ Expand All'}
				</button>
				<button onclick={collapseExpanded} disabled={!graphNodes.some(n => !n.inPath)}
					class="pt-button pt-button-outlined disabled:opacity-40 disabled:cursor-not-allowed">
					⊖ Collapse
				</button>
			</div>
		</div>
	{/if}

	<!-- ── Row 4: D3 canvas (clean — no overlay widgets) ── -->
	<section class="flex-1 relative overflow-hidden min-h-[35vh]"
	         style="background: var(--pt-bg-0);">

		<!-- Empty state -->
		{#if graphNodes.length === 0 && !pathLoading}
			<div class="absolute inset-0 flex items-center justify-center pointer-events-none">
				<div class="text-center space-y-2">
					<svg class="w-12 h-12 mx-auto" style="color: var(--pt-border);" fill="none" stroke="currentColor" stroke-width="1" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" d="M7.5 21L3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 12M21 7.5H7.5"/>
					</svg>
					{#if !source.selected && !target.selected}
						<p class="text-sm" style="color: var(--pt-text-muted);">Search for two people to find their connection</p>
					{:else if source.selected && !target.selected}
						<p class="text-sm" style="color: var(--pt-text-muted);">Now search for a target person</p>
					{:else if !source.selected && target.selected}
						<p class="text-sm" style="color: var(--pt-text-muted);">Now search for a source person</p>
					{:else}
						<p class="text-sm" style="color: var(--pt-text-muted);">Click "Find Connection" to search</p>
					{/if}
				</div>
			</div>
		{/if}

		<svg bind:this={svgEl} class="w-full h-full" style="display: block; touch-action: none;"></svg>

		<!-- Legend -->
		{#if ministryLegend.length > 0}
			<div class="absolute bottom-3 left-3 max-w-[180px] space-y-1.5 p-2.5"
			     style="background: var(--pt-bg-1); border: 1px solid var(--pt-border); border-radius: 2px;">
				<div class="flex items-center gap-1">
					<p class="pt-label">Ministry</p>
					<InfoTip tip="◆ diamond = ministry (root). ▬ rect = agency. Colours match across the graph." />
				</div>
				<ul class="space-y-1">
					{#each ministryLegend as item}
						<li class="flex items-center gap-1.5">
							<span class="w-2.5 h-2.5 shrink-0" style="background: {item.color}; border-radius: 1px;"></span>
							<span class="text-sm truncate" style="color: var(--pt-text-secondary);">{item.ministry}</span>
						</li>
					{/each}
				</ul>
			</div>
		{/if}

		{#if graphNodes.length > 0}
			<div class="absolute bottom-3 right-3 text-sm px-2.5 py-1.5 hidden sm:block"
			     style="color: var(--pt-text-muted); background: var(--pt-bg-1); border: 1px solid var(--pt-border); border-radius: 2px;">
				Click person · Scroll to zoom · Drag to pan
			</div>
		{/if}
	</section>
</div>

<!-- ── Hover tooltip ─────────────────────────────────── -->
{#if hoveredNode}
	{@const adjOrgs = graphEdges
		.filter(e => edgeEndpointId(e.source) === hoveredNode!.id || edgeEndpointId(e.target) === hoveredNode!.id)
		.map(e => {
			const otherId = edgeEndpointId(e.source) === hoveredNode!.id
				? edgeEndpointId(e.target) : edgeEndpointId(e.source);
			return graphNodes.find(n => n.id === otherId && n.type === 'org');
		})
		.filter((n): n is GNode => n != null)}
	<div
		class="fixed z-30 pointer-events-none max-w-56 space-y-1.5 p-3"
		style="left: {hoverClientX + 14}px; top: {hoverClientY - 70}px;
		       background: var(--pt-bg-2); border: 1px solid var(--pt-border); border-radius: 2px;
		       box-shadow: 0 4px 12px rgba(0,0,0,0.5);"
	>
		<p class="text-sm font-semibold leading-snug" style="color: var(--pt-text-primary);">{hoveredNode.name}</p>

		{#if hoveredNode.type === 'org'}
			{#if hoveredNode.agencyName && hoveredNode.ministry}
				<div class="space-y-0.5">
					<div class="flex items-center gap-1.5">
						<span class="w-2 h-2 shrink-0" style="background: {getMinistryColor(hoveredNode.ministry)}; border-radius: 1px;"></span>
						<p class="text-sm" style="color: var(--pt-text-secondary);">{hoveredNode.ministry}</p>
					</div>
					<p class="text-sm pl-3.5" style="color: var(--pt-text-muted);">↳ {hoveredNode.agencyName}</p>
				</div>
				<p class="pt-label">Agency</p>
			{:else if hoveredNode.ministry}
				<div class="flex items-center gap-1.5">
					<span class="w-2 h-2 rotate-45 shrink-0" style="background: {getMinistryColor(hoveredNode.ministry)};"></span>
					<p class="text-sm" style="color: var(--pt-text-secondary);">{hoveredNode.ministry}</p>
				</div>
				<p class="pt-label">Ministry</p>
			{/if}
		{:else}
			{#if hoveredNode.role}
				<p class="text-sm" style="color: var(--pt-text-secondary);">{hoveredNode.role}</p>
			{/if}
			{#if hoveredNode.ministry}
				<div class="flex items-center gap-1.5">
					<span class="w-2 h-2 shrink-0" style="background: {getMinistryColor(hoveredNode.ministry)}; border-radius: 1px;"></span>
					<p class="text-sm" style="color: var(--pt-text-muted);">{hoveredNode.ministry}</p>
				</div>
			{/if}
			{#if adjOrgs.length > 0}
				<div class="pt-1" style="border-top: 1px solid var(--pt-border-muted);">
					<p class="pt-label mb-1">Connected through</p>
					<ul class="space-y-0.5">
						{#each adjOrgs as org}
							<li class="flex items-center gap-1.5 text-sm" style="color: var(--pt-text-muted);">
								<span class="w-1.5 h-1.5 shrink-0" style="background: {org.ministry ? getMinistryColor(org.ministry) : '#5C7080'}; border-radius: 1px;"></span>
								<span class="truncate">{org.agencyName ?? org.ministry ?? org.name}</span>
							</li>
						{/each}
					</ul>
				</div>
			{/if}
			<p class="text-sm" style="color: var(--pt-text-muted);">
				{hoveredNode.isSource ? '▲ Source' : hoveredNode.isTarget ? '▼ Target' : hoveredNode.inPath ? 'Path node' : 'Expanded'}
				· Click for stats
			</p>
		{/if}
	</div>
{/if}

<!-- ── Node stats modal ─────────────────────────────── -->
{#if modalNode}
	<button
		class="fixed inset-0 z-40 bg-black/50"
		onclick={closeModal}
		aria-label="Close modal"
	></button>

	<div class="fixed z-50 top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2
	            w-full max-w-sm p-5 space-y-4"
	     style="background: var(--pt-bg-1); border: 1px solid var(--pt-border); border-radius: 2px;
	            box-shadow: 0 8px 32px rgba(0,0,0,0.6);">

		<div class="flex items-start justify-between gap-3">
			<div class="flex items-center gap-3">
				<div class="w-10 h-10 flex items-center justify-center text-white text-sm font-bold shrink-0"
				     style="background: {personFill(modalNode)}; border-radius: 2px; font-family: var(--font-mono);">
					{modalNode.name.slice(0, 2).toUpperCase()}
				</div>
				<div>
					<h2 class="text-sm font-semibold" style="color: var(--pt-text-primary);">{modalNode.name}</h2>
					{#if modalNode.role}
						<p class="text-sm mt-0.5" style="color: var(--pt-text-muted);">{modalNode.role}</p>
					{/if}
					{#if modalNode.ministry}
						<div class="flex items-center gap-1.5 mt-0.5">
							<span class="w-2 h-2" style="background: {getMinistryColor(modalNode.ministry)}; border-radius: 1px;"></span>
							<p class="text-sm" style="color: var(--pt-text-muted);">{modalNode.ministry}</p>
						</div>
					{/if}
				</div>
			</div>
			<button onclick={closeModal}
				class="w-7 h-7 flex items-center justify-center transition-colors shrink-0"
				style="color: var(--pt-text-muted); border-radius: 2px;"
				aria-label="Close">
				<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/>
				</svg>
			</button>
		</div>

		{#if modalLoading}
			<div class="space-y-2">
				<div class="h-14 rounded animate-pulse" style="background: var(--pt-bg-2);"></div>
				<div class="h-24 rounded animate-pulse" style="background: var(--pt-bg-2);"></div>
			</div>
		{:else if modalNetwork}
			<div class="grid grid-cols-2 gap-2">
				<div class="p-3 text-center" style="background: var(--pt-bg-2); border-radius: 2px;">
					<p class="text-xl font-bold tabular-nums pt-data" style="color: var(--pt-text-primary);">
						{modalNetwork.summary.total_colleagues}
					</p>
					<p class="text-sm mt-0.5" style="color: var(--pt-text-muted);">Direct connections</p>
				</div>
				<div class="p-3 text-center" style="background: var(--pt-bg-2); border-radius: 2px;">
					<p class="text-xl font-bold tabular-nums pt-data" style="color: var(--pt-text-primary);">
						{ministryCounts.length}
					</p>
					<p class="text-sm mt-0.5" style="color: var(--pt-text-muted);">
						{ministryCounts.length === 1 ? 'Ministry' : 'Ministries'}
					</p>
				</div>
			</div>

			{#if ministryCounts.length > 0}
				<div>
					<p class="pt-label mb-2">Connections by ministry</p>
					<ul class="space-y-1.5 max-h-40 overflow-y-auto">
						{#each ministryCounts as m}
							<li class="flex items-center gap-2">
								<span class="w-2.5 h-2.5 shrink-0" style="background: {getMinistryColor(m.ministry)}; border-radius: 1px;"></span>
								<span class="text-sm truncate flex-1" style="color: var(--pt-text-secondary);">{m.ministry}</span>
								<span class="text-sm font-semibold tabular-nums shrink-0 pt-data px-1.5 py-0.5"
								      style="background: var(--pt-bg-3); color: var(--pt-text-secondary); border-radius: 2px;">
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
			class="pt-button w-full justify-center {modalNode.expanded ? 'pt-button-outlined' : 'pt-button-primary'}"
			style={modalNode.expanded ? 'opacity: 0.5; cursor: not-allowed;' : ''}>
			{modalNode.expanded ? 'Already expanded' : 'Expand in graph'}
		</button>
	</div>
{/if}
