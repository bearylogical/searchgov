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
		const ro = new ResizeObserver(entries => {
			for (const e of entries) { svgWidth = e.contentRect.width; svgHeight = e.contentRect.height; }
		});
		if (svgEl?.parentElement) ro.observe(svgEl.parentElement);
		return () => { document.body.style.overflow = ''; ro.disconnect(); };
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

	function orgFill(d: GNode): string {
		return d.ministry ? getMinistryColor(d.ministry) : (d.inPath ? '#6366f1' : '#94a3b8');
	}

	function renderD3() {
		if (!svgEl) return;
		const svg = d3.select(svgEl);
		svg.selectAll('*').remove();

		// Defs: drop shadow
		const defs = svg.append('defs');
		const shadow = defs.append('filter')
			.attr('id', 'node-shadow').attr('x', '-20%').attr('y', '-20%').attr('width', '140%').attr('height', '140%');
		shadow.append('feDropShadow').attr('dx', 0).attr('dy', 1).attr('stdDeviation', 2).attr('flood-opacity', 0.18);

		const g = svg.append('g');

		svg.call(
			d3.zoom<SVGSVGElement, unknown>()
				.scaleExtent([0.15, 5])
				.on('zoom', e => g.attr('transform', e.transform))
		);

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
			const margin = svgWidth * 0.1;
			const span   = svgWidth - 2 * margin;
			simNodes.forEach(n => {
				const idx = pathNodeIds.indexOf(n.id);
				if (idx !== -1) {
					n.x = margin + (idx / (totalPath - 1)) * span;
					n.y = svgHeight / 2 + (idx % 2 === 0 ? -20 : 20);
				}
			});
		}

		simulation = d3.forceSimulation<GNode>(simNodes)
			.alpha(hasPositions ? 0.15 : 0.8)
			.force('link',    d3.forceLink<GNode, GEdge>(simEdges).id(d => d.id).distance(d => d.inPath ? 140 : 90))
			.force('charge',  d3.forceManyBody().strength(-500))
			.force('center',  d3.forceCenter(svgWidth / 2, svgHeight / 2).strength(0.05))
			.force('collide', d3.forceCollide<GNode>(d => nodeRadius(d) + 16))
			// Gentle left-to-right ordering for path nodes to suppress crossings
			.force('path-x',  d3.forceX<GNode>(d => {
				const idx = pathNodeIds.indexOf(d.id);
				if (idx === -1) return svgWidth / 2;
				const margin = svgWidth * 0.1;
				return margin + (idx / Math.max(totalPath - 1, 1)) * (svgWidth - 2 * margin);
			}).strength(d => d.inPath ? 0.2 : 0.01))
			.force('path-y',  d3.forceY<GNode>(svgHeight / 2).strength(d => d.inPath ? 0.1 : 0.01));

		// ── Links ──────────────────────────────────────────
		const link = g.append('g').attr('class', 'links')
			.selectAll<SVGLineElement, GEdge>('line')
			.data(simEdges)
			.join('line')
			.attr('stroke',          d => d.inPath ? '#818cf8' : '#cbd5e1')
			.attr('stroke-width',    d => d.inPath ? 2.5 : 1.2)
			.attr('stroke-dasharray',d => d.inPath ? null : '5,4')
			.attr('opacity',         d => d.inPath ? 1 : 0.45);

		// ── Edge year labels ───────────────────────────────
		const edgeLabel = g.append('g').attr('class', 'edge-labels')
			.selectAll<SVGTextElement, GEdge>('text')
			.data(simEdges.filter(e => e.yearLabel))
			.join('text')
			.attr('text-anchor', 'middle')
			.attr('font-size', '10px')
			.attr('font-weight', '500')
			.attr('fill', '#6366f1')
			// White halo for readability over the edge line
			.style('paint-order', 'stroke')
			.attr('stroke', 'white')
			.attr('stroke-width', 3)
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
			.attr('fill', 'white').attr('font-size', '13px').attr('font-weight', '700')
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
			.attr('fill', 'white').attr('font-size', '9px').attr('font-weight', '600')
			.attr('pointer-events', 'none')
			.text(d => truncate(d.agencyName ?? d.ministry ?? d.name, 13));

		// ── Name labels below nodes ─────────────────────────
		// Person nodes: single line (name only)
		personNodes.append('text')
			.attr('text-anchor', 'middle')
			.attr('y', d => nodeRadius(d) + 17)
			.attr('fill', '#1f2937').attr('font-size', '12px')
			.attr('font-weight', d => (d.isSource || d.isTarget) ? '700' : '500')
			.attr('pointer-events', 'none')
			.text(d => truncate(d.name, 24));

		// Org nodes: 2-line (org name + ministry in smaller text for agencies)
		orgNodes.each(function(d) {
			const yBase = d.isMinistry ? 32 : 28;
			const text = d3.select<SVGGElement, GNode>(this).append('text')
				.attr('text-anchor', 'middle')
				.attr('pointer-events', 'none');
			text.append('tspan')
				.attr('x', 0).attr('y', yBase)
				.attr('fill', '#1f2937').attr('font-size', '11px').attr('font-weight', '500')
				.text(truncate(d.agencyName ?? d.name, 22));
			if (d.agencyName && d.ministry) {
				text.append('tspan')
					.attr('x', 0).attr('dy', '1.25em')
					.attr('fill', getMinistryColor(d.ministry))
					.attr('font-size', '9px')
					.text(truncate(d.ministry, 22));
			}
		});

		// Source / Target label
		personNodes.filter(d => d.isSource || d.isTarget)
			.append('text')
			.attr('text-anchor', 'middle')
			.attr('y', d => nodeRadius(d) + 34)
			.attr('fill', d => d.isSource ? '#2563eb' : '#059669')
			.attr('font-size', '11px').attr('font-weight', '700').attr('letter-spacing', '0.3px')
			.attr('pointer-events', 'none')
			.text(d => d.isSource ? '▲ Source' : '▼ Target');

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
		pathResult = null; pathError = ''; graphNodes = []; graphEdges = [];
		nodePositions.clear(); edgeYearCache.clear();
	}
</script>

<div class="flex flex-col lg:flex-row overflow-hidden" style="height: calc(100vh - 3.5rem)">

	<!-- ── Left sidebar ─────────────────────────────────── -->
	<aside class="w-full lg:w-80 xl:w-96 shrink-0 flex flex-col border-b lg:border-b-0 lg:border-r
	              border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 overflow-y-auto">

		<div class="p-4 border-b border-gray-100 dark:border-gray-800 space-y-3">
			<div class="flex items-center justify-between">
				<h1 class="text-base font-semibold text-gray-900 dark:text-gray-100">Connectivity Explorer</h1>
				<InfoTip tip="Find the shortest connection path between two people through shared organisations. Click any person node to view their network stats." />
			</div>

			<ConfidenceSlider bind:value={confidenceThreshold} />

			<label class="flex items-center gap-2 cursor-pointer group">
				<input type="checkbox" bind:checked={temporal}
					onchange={() => { if (source.selected && target.selected) findPath(); }}
					class="rounded accent-blue-600 w-3.5 h-3.5"/>
				<span class="text-sm text-gray-600 dark:text-gray-400 group-hover:text-gray-800 dark:group-hover:text-gray-200 transition-colors">
					Temporal (actual co-workers only)
				</span>
				<InfoTip tip="When on, only finds connections where people were physically working together at the same time. Turn off to allow any historical connection." />
			</label>
		</div>

		<!-- Source slot -->
		<div class="p-4 border-b border-gray-100 dark:border-gray-800 space-y-3">
			<div class="flex items-center gap-1.5">
				<span class="w-2.5 h-2.5 rounded-full bg-blue-500 shrink-0"></span>
				<p class="text-sm font-semibold text-blue-600 dark:text-blue-400 uppercase tracking-wide">Source</p>
				<InfoTip tip="The person you're tracing FROM. Drag variants between zones to fine-tune which name spellings are included in the search." />
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
		<div class="p-4 space-y-3">
			<div class="flex items-center gap-1.5">
				<span class="w-2.5 h-2.5 rounded-full border-2 border-dashed border-emerald-500 shrink-0"></span>
				<p class="text-sm font-semibold text-emerald-600 dark:text-emerald-400 uppercase tracking-wide">Target</p>
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

		<!-- Status / stat cards / toolbar -->
		{#if pathResult || pathLoading || pathError}
			<div class="absolute top-3 left-1/2 -translate-x-1/2 z-10 flex flex-col items-center gap-2 w-full max-w-xl px-3">
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
					<!-- Stat cards row -->
					<div class="flex gap-2.5 flex-wrap justify-center">
						<div class="bg-white dark:bg-gray-900 border border-indigo-100 dark:border-indigo-900
						            rounded-2xl px-5 py-3 shadow-sm text-center min-w-[80px]">
							<p class="text-3xl font-bold text-indigo-600 dark:text-indigo-400 tabular-nums leading-none">{degreeBadge}</p>
							<p class="text-[11px] text-gray-500 dark:text-gray-400 mt-1.5 uppercase tracking-wide font-medium">
								{degreeBadge === 1 ? 'Degree' : 'Degrees'}
							</p>
						</div>
						{#if connectionStats.ministries > 0}
							<div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700
							            rounded-2xl px-5 py-3 shadow-sm text-center min-w-[80px]">
								<p class="text-3xl font-bold text-gray-800 dark:text-gray-100 tabular-nums leading-none">{connectionStats.ministries}</p>
								<p class="text-[11px] text-gray-500 dark:text-gray-400 mt-1.5 uppercase tracking-wide font-medium">
									{connectionStats.ministries === 1 ? 'Ministry' : 'Ministries'}
								</p>
							</div>
						{/if}
						{#if connectionStats.agencies > 0}
							<div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700
							            rounded-2xl px-5 py-3 shadow-sm text-center min-w-[80px]">
								<p class="text-3xl font-bold text-gray-800 dark:text-gray-100 tabular-nums leading-none">{connectionStats.agencies}</p>
								<p class="text-[11px] text-gray-500 dark:text-gray-400 mt-1.5 uppercase tracking-wide font-medium">
									{connectionStats.agencies === 1 ? 'Agency' : 'Agencies'}
								</p>
							</div>
						{/if}
						{#if overlapTimeline}
							<div class="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700
							            rounded-2xl px-5 py-3 shadow-sm text-center min-w-[96px]">
								<p class="text-2xl font-bold text-gray-800 dark:text-gray-100 tabular-nums leading-none">{overlapTimeline}</p>
								<p class="text-[11px] text-gray-500 dark:text-gray-400 mt-1.5 uppercase tracking-wide font-medium">Timeline</p>
							</div>
						{/if}
					</div>
					<!-- Graph control buttons -->
					<div class="flex gap-1.5 flex-wrap justify-center">
						<button onclick={resetGraph}
							class="flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-lg
							       bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700
							       text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800
							       shadow-sm transition-colors">
							↺ Reset
						</button>
						<button onclick={expandAllNodes} disabled={expandingAll}
							class="flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-lg
							       bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700
							       text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800
							       shadow-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed">
							{expandingAll ? '⏳ Expanding…' : '⊕ Expand All'}
						</button>
						<button onclick={collapseExpanded}
							disabled={!graphNodes.some(n => !n.inPath)}
							class="flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-lg
							       bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700
							       text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800
							       shadow-sm transition-colors disabled:opacity-40 disabled:cursor-not-allowed">
							⊖ Collapse
						</button>
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

		<!-- Legend -->
		{#if ministryLegend.length > 0}
			<div class="absolute bottom-4 left-4 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700
			            rounded-xl px-3 py-2.5 shadow-sm max-w-[200px] space-y-2">
				<div class="flex items-center gap-1.5">
					<p class="text-[10px] font-semibold uppercase tracking-wide text-gray-400">Ministry</p>
					<InfoTip tip="◆ diamond = ministry (root). ▬ rect = agency under that ministry. Colours match across the graph." />
				</div>
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

		{#if graphNodes.length > 0}
			<div class="absolute bottom-4 right-4 text-xs text-gray-400 dark:text-gray-600
			            bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700
			            rounded-lg px-3 py-2 shadow-sm">
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
		class="fixed z-30 pointer-events-none max-w-60 rounded-xl border border-gray-200 dark:border-gray-700
		       bg-white dark:bg-gray-900 shadow-xl px-3.5 py-2.5 space-y-1.5"
		style="left: {hoverClientX + 14}px; top: {hoverClientY - 70}px;"
	>
		<p class="text-sm font-semibold text-gray-900 dark:text-gray-100 leading-snug">{hoveredNode.name}</p>

		{#if hoveredNode.type === 'org'}
			<!-- Org tooltip -->
			{#if hoveredNode.agencyName && hoveredNode.ministry}
				<div class="space-y-0.5">
					<div class="flex items-center gap-1.5">
						<span class="w-2.5 h-2.5 rounded-sm shrink-0" style="background: {getMinistryColor(hoveredNode.ministry)}"></span>
						<p class="text-xs font-medium text-gray-700 dark:text-gray-300">{hoveredNode.ministry}</p>
					</div>
					<p class="text-xs text-gray-400 pl-4">↳ {hoveredNode.agencyName}</p>
				</div>
				<p class="text-[10px] uppercase tracking-wide text-gray-400 font-semibold">Agency</p>
			{:else if hoveredNode.ministry}
				<div class="flex items-center gap-1.5">
					<span class="w-2.5 h-2.5 rotate-45 shrink-0" style="background: {getMinistryColor(hoveredNode.ministry)}"></span>
					<p class="text-xs text-gray-500 dark:text-gray-400">{hoveredNode.ministry}</p>
				</div>
				<p class="text-[10px] uppercase tracking-wide text-gray-400 font-semibold">Ministry</p>
			{/if}
		{:else}
			<!-- Person tooltip -->
			{#if hoveredNode.role}
				<p class="text-xs text-gray-600 dark:text-gray-400">{hoveredNode.role}</p>
			{/if}
			{#if hoveredNode.ministry}
				<div class="flex items-center gap-1.5">
					<span class="w-2.5 h-2.5 rounded-sm shrink-0" style="background: {getMinistryColor(hoveredNode.ministry)}"></span>
					<p class="text-xs text-gray-500 dark:text-gray-400">{hoveredNode.ministry}</p>
				</div>
			{/if}
			{#if adjOrgs.length > 0}
				<div class="border-t border-gray-100 dark:border-gray-800 pt-1.5">
					<p class="text-[10px] uppercase tracking-wide text-gray-400 font-semibold mb-1">Connected through</p>
					<ul class="space-y-0.5">
						{#each adjOrgs as org}
							<li class="flex items-center gap-1.5 text-xs text-gray-600 dark:text-gray-400">
								<span class="w-2 h-2 rounded-sm shrink-0"
								      style="background: {org.ministry ? getMinistryColor(org.ministry) : '#94a3b8'}"></span>
								<span class="truncate">{org.agencyName ?? org.ministry ?? org.name}</span>
							</li>
						{/each}
					</ul>
				</div>
			{/if}
			<p class="text-xs text-gray-400 dark:text-gray-500">
				{hoveredNode.isSource ? '▲ Source' : hoveredNode.isTarget ? '▼ Target' : hoveredNode.inPath ? 'Path node' : 'Expanded'}
				· Click for stats
			</p>
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

		<div class="flex items-start justify-between gap-3">
			<div class="flex items-center gap-3">
				<div class="w-11 h-11 rounded-full flex items-center justify-center text-white text-sm font-bold shrink-0"
				     style="background: {personFill(modalNode)}">
					{modalNode.name.slice(0, 2).toUpperCase()}
				</div>
				<div>
					<h2 class="font-semibold text-gray-900 dark:text-gray-100 text-base">{modalNode.name}</h2>
					{#if modalNode.role}
						<p class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{modalNode.role}</p>
					{/if}
					{#if modalNode.ministry}
						<div class="flex items-center gap-1.5 mt-0.5">
							<span class="w-2 h-2 rounded-sm" style="background: {getMinistryColor(modalNode.ministry)}"></span>
							<p class="text-xs text-gray-500 dark:text-gray-400">{modalNode.ministry}</p>
						</div>
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
