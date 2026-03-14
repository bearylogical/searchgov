<script lang="ts">
	import { people } from '$lib/api';
	import type { PersonResult, EmploymentEntry } from '$lib/api';
	import { isAuthenticated } from '$lib/auth';
	import { goto } from '$app/navigation';

	// Redirect to login if not authenticated.
	if (!$isAuthenticated) goto('/login?redirect=/progression');

	let query = $state('');
	let results = $state<PersonResult[]>([]);
	let selected = $state<PersonResult | null>(null);
	let career = $state<EmploymentEntry[]>([]);
	let searching = $state(false);
	let loadingCareer = $state(false);
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
			results = await people.search(query);
		} catch (err: unknown) {
			searchError = err instanceof Error ? err.message : 'Search failed';
		} finally {
			searching = false;
		}
	}

	async function selectPerson(person: PersonResult) {
		selected = person;
		career = [];
		loadingCareer = true;
		try {
			career = await people.career(person.person_id);
		} finally {
			loadingCareer = false;
		}
	}

	function formatDate(d: string | null) {
		if (!d) return '—';
		return new Date(d).toLocaleDateString('en-SG', {
			year: 'numeric',
			month: 'short'
		});
	}
</script>

<h1 class="text-2xl font-bold text-gray-900 mb-6">Career Progression</h1>

<!-- Search -->
<div class="flex gap-2 mb-4">
	<input
		type="text"
		placeholder="Search by name…"
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
		{#each results as person}
			<li>
				<button
					class="w-full text-left px-4 py-3 hover:bg-gray-50 transition-colors"
					onclick={() => selectPerson(person)}
				>
					<span class="font-medium text-gray-900 text-sm">{person.name}</span>
					{#if person.email}
						<span class="text-xs text-gray-400 ml-2">{person.email}</span>
					{/if}
				</button>
			</li>
		{/each}
	</ul>
{/if}

<!-- Selected person + career timeline -->
{#if selected}
	<div class="mb-6">
		<div class="flex items-center gap-3 mb-4">
			<button
				onclick={() => { selected = null; career = []; }}
				class="text-sm text-blue-600 hover:text-blue-800"
			>
				← Back
			</button>
			<h2 class="font-semibold text-gray-900">{selected.name}</h2>
			{#if selected.email}
				<span class="text-sm text-gray-400">{selected.email}</span>
			{/if}
		</div>

		{#if loadingCareer}
			<p class="text-sm text-gray-400">Loading career history…</p>
		{:else if career.length === 0}
			<p class="text-sm text-gray-400">No career history found.</p>
		{:else}
			<div class="relative">
				<!-- Timeline line -->
				<div class="absolute left-3 top-0 bottom-0 w-px bg-gray-200"></div>

				<ul class="space-y-4">
					{#each career as entry}
						<li class="pl-10 relative">
							<div class="absolute left-1.5 top-1.5 w-3 h-3 rounded-full bg-blue-500 border-2 border-white shadow"></div>
							<div class="bg-white border border-gray-200 rounded-lg p-4 shadow-sm">
								<p class="font-medium text-gray-900 text-sm">{entry.org_name}</p>
								{#if entry.rank}
									<p class="text-sm text-gray-600 mt-0.5">{entry.rank}</p>
								{/if}
								<p class="text-xs text-gray-400 mt-1">
									{formatDate(entry.start_date)} – {formatDate(entry.end_date)}
									{#if entry.tenure_days}
										&nbsp;·&nbsp;{Math.round(entry.tenure_days / 30)} mo
									{/if}
								</p>
							</div>
						</li>
					{/each}
				</ul>
			</div>
		{/if}
	</div>
{/if}
