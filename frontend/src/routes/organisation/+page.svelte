<script lang="ts">
	import { organisations } from '$lib/api';
	import type { OrgResult } from '$lib/api';
	import { isAuthenticated } from '$lib/auth';
	import { goto } from '$app/navigation';

	// Reactive guard — runs on mount and whenever auth state changes.
	$effect(() => {
		if (!$isAuthenticated) goto('/login?redirect=/organisation');
	});

	let query = $state('');
	let results = $state<OrgResult[]>([]);
	let selected = $state<OrgResult | null>(null);
	let tree = $state<OrgResult[]>([]);
	let timeline = $state<string[]>([]);
	let selectedDate = $state('');
	let searching = $state(false);
	let loadingTree = $state(false);
	let searchError = $state('');

	let searchTimeout: ReturnType<typeof setTimeout>;

	function onQueryInput() {
		clearTimeout(searchTimeout);
		if (!query.trim()) {
			results = [];
			return;
		}
		searchTimeout = setTimeout(runSearch, 300);
	}

	async function runSearch() {
		searching = true;
		searchError = '';
		try {
			results = await organisations.search(query);
		} catch (err: unknown) {
			searchError = err instanceof Error ? err.message : 'Search failed';
		} finally {
			searching = false;
		}
	}

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
			if (timeline.length > 0) selectedDate = timeline[timeline.length - 1];
		} finally {
			loadingTree = false;
		}
	}

	async function loadTreeAtDate() {
		if (!selected) return;
		loadingTree = true;
		try {
			tree = await organisations.tree(selected.id, selectedDate);
		} finally {
			loadingTree = false;
		}
	}
</script>

<h1 class="text-2xl font-bold text-gray-900 mb-6">Organisation Explorer</h1>

<!-- Search -->
<div class="flex gap-2 mb-4">
	<input
		type="text"
		placeholder="Search by organisation name…"
		bind:value={query}
		oninput={onQueryInput}
		class="flex-1 border border-gray-300 rounded px-3 py-2 text-sm
			focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
	/>
	{#if searching}
		<span class="text-sm text-gray-400 self-center">Searching…</span>
	{/if}
</div>

{#if searchError}
	<p class="text-sm text-red-600 mb-4">{searchError}</p>
{/if}

<!-- Results list -->
{#if results.length > 0 && !selected}
	<ul class="bg-white border border-gray-200 rounded-lg divide-y divide-gray-100 mb-6 shadow-sm">
		{#each results as org}
			<li>
				<button
					class="w-full text-left px-4 py-3 hover:bg-gray-50 transition-colors"
					onclick={() => selectOrg(org)}
				>
					<span class="font-medium text-gray-900 text-sm">{org.name}</span>
					{#if org.department}
						<span class="text-xs text-gray-400 ml-2">{org.department}</span>
					{/if}
				</button>
			</li>
		{/each}
	</ul>
{/if}

<!-- Selected org + subtree -->
{#if selected}
	<div>
		<div class="flex items-center gap-3 mb-4">
			<button
				onclick={() => { selected = null; tree = []; timeline = []; }}
				class="text-sm text-blue-600 hover:text-blue-800"
			>
				← Back
			</button>
			<h2 class="font-semibold text-gray-900">{selected.name}</h2>
		</div>

		<!-- Date picker -->
		{#if timeline.length > 0}
			<div class="flex items-center gap-3 mb-4">
				<label for="date-select" class="text-sm text-gray-600">View at:</label>
				<select
					id="date-select"
					bind:value={selectedDate}
					onchange={loadTreeAtDate}
					class="border border-gray-300 rounded px-2 py-1 text-sm
						focus:outline-none focus:ring-2 focus:ring-blue-500"
				>
					{#each timeline as d}
						<option value={d}>{d}</option>
					{/each}
				</select>
			</div>
		{/if}

		{#if loadingTree}
			<p class="text-sm text-gray-400">Loading…</p>
		{:else if tree.length === 0}
			<p class="text-sm text-gray-400">No sub-organisations found.</p>
		{:else}
			<ul class="space-y-2">
				{#each tree as child}
					<li class="bg-white border border-gray-200 rounded-lg px-4 py-3 shadow-sm">
						<p class="font-medium text-gray-900 text-sm">{child.name}</p>
						{#if child.department}
							<p class="text-xs text-gray-400 mt-0.5">{child.department}</p>
						{/if}
					</li>
				{/each}
			</ul>
		{/if}
	</div>
{/if}
