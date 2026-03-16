<script lang="ts">
	import { people } from '$lib/api';
	import type { PersonResult, EmploymentEntry, NameVariant } from '$lib/api';
	import { isAuthenticated, authReady } from '$lib/auth';
	import { goto } from '$app/navigation';
	import ConfidenceSlider from '$lib/components/ConfidenceSlider.svelte';
	import NameVariantZones from '$lib/components/NameVariantZones.svelte';
	import PersonSearch from '$lib/components/PersonSearch.svelte';

	$effect(() => {
		if ($authReady && !$isAuthenticated) goto('/login?redirect=/progression');
	});

	// ---------------------------------------------------------------------------
	// State
	// ---------------------------------------------------------------------------
	let selected        = $state<PersonResult | null>(null);
	let originalCareer  = $state<EmploymentEntry[]>([]);
	let career          = $state<EmploymentEntry[]>([]);
	let nameVariants    = $state<NameVariant[]>([]);
	let activeNames     = $state<Set<string>>(new Set());

	let loadingCareer   = $state(false);
	let careerError     = $state('');

	let confidenceThreshold = $state(95);

	// ---------------------------------------------------------------------------
	// Select person
	// ---------------------------------------------------------------------------
	async function selectPerson(person: PersonResult) {
		selected = person; career = []; originalCareer = []; nameVariants = []; activeNames = new Set();
		careerError = ''; loadingCareer = true;
		try { await loadCareerFor(person.name); }
		finally { loadingCareer = false; }
	}

	const BROAD_THRESHOLD = 0.5;

	async function loadCareerFor(name: string) {
		const [variants, raw] = await Promise.all([
			people.similarNames(name, 15, BROAD_THRESHOLD),
			people.careerByName(name, true, BROAD_THRESHOLD)
		]);
		nameVariants = variants;
		const sorted = [...raw].sort((a, b) => {
			if (!a.start_date) return 1;
			if (!b.start_date) return -1;
			return a.start_date.localeCompare(b.start_date);
		});
		originalCareer = sorted;
		const highConf = new Set(variants.filter(v => v.score >= confidenceThreshold).map(v => v.name));
		activeNames = highConf;
		career = sorted.filter(e => !e.person_name || highConf.has(e.person_name));
	}

	function clearSelection() {
		selected = null; career = []; originalCareer = []; nameVariants = []; activeNames = new Set();
	}

	// ---------------------------------------------------------------------------
	// Derived helpers
	// ---------------------------------------------------------------------------
	const variantScoreMap = $derived(new Map(nameVariants.map(v => [v.name, v.score])));

	const defaultActiveNames = $derived(
		new Set(nameVariants.filter(v => v.score >= confidenceThreshold).map(v => v.name))
	);

	const expectedCareerLength = $derived(
		originalCareer.filter(e => !e.person_name || activeNames.has(e.person_name)).length
	);

	const isDirty = $derived(
		activeNames.size !== defaultActiveNames.size ||
		[...activeNames].some(n => !defaultActiveNames.has(n)) ||
		career.length < expectedCareerLength
	);

	function isLowConfidence(entry: EmploymentEntry): boolean {
		if (!entry.person_name) return false;
		const score = variantScoreMap.get(entry.person_name);
		return score !== undefined && score < confidenceThreshold;
	}

	// ---------------------------------------------------------------------------
	// Toggle variant
	// ---------------------------------------------------------------------------
	function toggleName(name: string) {
		const next = new Set(activeNames);
		if (next.has(name)) { next.delete(name); } else { next.add(name); }
		activeNames = next;
		const removedIds = new Set(
			originalCareer.filter(e => !career.some(c => c.id === e.id)).map(e => e.id)
		);
		career = originalCareer.filter(
			e => !removedIds.has(e.id) && (!e.person_name || next.has(e.person_name))
		);
	}

	function removeEntry(entry: EmploymentEntry) {
		career = career.filter(e => e !== entry);
	}

	function reset() {
		activeNames = new Set(defaultActiveNames);
		career = originalCareer.filter(e => !e.person_name || defaultActiveNames.has(e.person_name));
	}

	// ---------------------------------------------------------------------------
	// Profile stats
	// ---------------------------------------------------------------------------
	const employmentSpan = $derived(() => {
		const starts = career.map(e => e.start_date).filter(Boolean) as string[];
		const ends   = career.map(e => e.end_date).filter(Boolean) as string[];
		return {
			from: starts.length ? formatDate(starts[0]) : null,
			to: career.some(e => !e.end_date) ? 'Present' : (ends.length ? formatDate(ends[ends.length - 1]) : null)
		};
	});

	const distinctOrgs = $derived([...new Set(career.map(e => orgLabel(e)))]);

	// ---------------------------------------------------------------------------
	// Helpers
	// ---------------------------------------------------------------------------
	function formatDate(d: string | null) {
		if (!d) return 'Present';
		return new Date(d).toLocaleDateString('en-SG', { year: 'numeric', month: 'short' });
	}

	function formatDuration(days: number | null) {
		if (!days) return null;
		const months = Math.round(days / 30.44);
		if (months < 12) return `${months}mo`;
		const years = Math.floor(months / 12);
		const rem = months % 12;
		return rem > 0 ? `${years}y ${rem}mo` : `${years}y`;
	}

	function orgLabel(e: EmploymentEntry) { return e.org_name ?? e.entity_name ?? 'Unknown organisation'; }
	function isActive(e: EmploymentEntry) { return !e.end_date; }
	function isSamePerson(e: EmploymentEntry) { return !selected || e.person_id == null || e.person_id === selected.id; }
</script>

<div class="flex-1 flex flex-col lg:flex-row min-h-0">
	<!-- ── Left panel ─────────────────────────────────── -->
	<aside class="w-full lg:w-80 xl:w-96 shrink-0 flex flex-col"
	       style="background: var(--pt-bg-1); border-right: 1px solid var(--pt-border);">
		<div class="p-4 space-y-3 flex-none" style="border-bottom: 1px solid var(--pt-border-muted);">
			<h1 class="pt-label">Career Progression</h1>

			<PersonSearch
				placeholder="Search by name…"
				{confidenceThreshold}
				{selected}
				onselect={selectPerson}
				onclear={clearSelection}
			/>

			<ConfidenceSlider bind:value={confidenceThreshold} />
		</div>

		<!-- Name variants (shown below search when selected) -->
		{#if selected && !loadingCareer && nameVariants.length > 0}
			<div class="p-4 space-y-2 overflow-y-auto lg:max-h-none" style="border-bottom: 1px solid var(--pt-border-muted); max-height: 35vh;">
				<div class="flex items-center justify-between">
					<p class="pt-label">Name variants</p>
					{#if isDirty}
						<button onclick={reset} class="text-xs transition-colors"
						        style="color: var(--pt-blue);">
							Reset
						</button>
					{/if}
				</div>
				<p class="text-xs" style="color: var(--pt-text-muted);">Drag between zones to adjust timeline</p>
				<NameVariantZones
					{nameVariants}
					{activeNames}
					{confidenceThreshold}
					ontoggle={toggleName}
				/>
			</div>
		{/if}
	</aside>

	<!-- ── Right panel ────────────────────────────────── -->
	<section class="flex-1 overflow-y-auto" style="background: var(--pt-bg-0);">
		{#if !selected}
			<div class="flex items-center justify-center p-8 min-h-[50vh]">
				<div class="text-center">
					<svg class="w-10 h-10 mx-auto mb-3" style="color: var(--pt-border);"
					     fill="none" stroke="currentColor" stroke-width="1" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z"/>
					</svg>
					<p class="text-sm" style="color: var(--pt-text-muted);">Select a person to view their career history</p>
				</div>
			</div>
		{:else}
			<div class="p-4 space-y-4">

				<!-- Profile header -->
				<div class="pt-card">
					<div class="flex items-center gap-3">
						<!-- Blueprint-style monogram: flat square, not circle -->
						<div class="w-10 h-10 flex items-center justify-center text-white font-bold text-sm shrink-0"
						     style="background: var(--pt-blue); border-radius: 2px; font-family: var(--font-mono);">
							{selected.name.slice(0, 2).toUpperCase()}
						</div>
						<div class="min-w-0 flex-1">
							<h2 class="text-sm font-semibold leading-snug" style="color: var(--pt-text-primary);">{selected.name}</h2>
							{#if selected.email}<p class="text-xs truncate mt-0.5" style="color: var(--pt-text-muted);">{selected.email}</p>{/if}
							{#if selected.tel}<p class="text-xs mt-0.5 pt-data" style="color: var(--pt-text-muted);">{selected.tel}</p>{/if}
						</div>
						{#if !loadingCareer && career.length > 0}
							<div class="shrink-0 text-right">
								<p class="text-base font-bold pt-data" style="color: var(--pt-text-primary);">{career.length}</p>
								<p class="text-xs" style="color: var(--pt-text-muted);">{career.length !== originalCareer.length ? `of ${originalCareer.length} ` : ''}roles</p>
							</div>
						{/if}
					</div>
				</div>

				{#if loadingCareer}
					<div class="grid grid-cols-1 xl:grid-cols-2 gap-4">
						<div class="space-y-2">
							{#each Array(5) as _}
								<div class="flex gap-4">
									<div class="w-2.5 h-2.5 rounded-full mt-1.5 animate-pulse shrink-0" style="background: var(--pt-bg-3);"></div>
									<div class="flex-1 h-16 rounded animate-pulse" style="background: var(--pt-bg-2);"></div>
								</div>
							{/each}
						</div>
						<div class="h-48 rounded animate-pulse" style="background: var(--pt-bg-2);"></div>
					</div>
				{:else if careerError}
					<div class="text-center py-12">
						<p class="text-sm" style="color: var(--pt-red);">{careerError}</p>
					</div>
				{:else if career.length === 0}
					<div class="text-center py-12">
						<p class="text-sm mb-3" style="color: var(--pt-text-muted);">No records match the current filters.</p>
						{#if isDirty}
							<button onclick={reset} class="text-sm" style="color: var(--pt-blue);">Reset filters</button>
						{/if}
					</div>
				{:else}
					<div class="grid grid-cols-1 xl:grid-cols-2 gap-4 items-start">

						<!-- ── Career Timeline ──────────── -->
						<div>
							<h3 class="pt-label mb-3">Career Timeline</h3>
							<div class="relative">
								<div class="absolute left-[5px] top-2 bottom-2 w-px" style="background: var(--pt-border-muted);"></div>
								<ul class="space-y-2">
									{#each career as entry}
										<li class="pl-7 relative group {!isSamePerson(entry) ? 'opacity-60' : ''}">
											<!-- Timeline dot -->
											<div class="absolute left-0 top-3.5 w-[11px] h-[11px] border-2"
											     style="border-radius: 50%; border-color: var(--pt-bg-0);
											            box-shadow: 0 0 0 1px {isSamePerson(entry) ? (isActive(entry) ? 'var(--pt-green)' : 'var(--pt-border)') : 'var(--pt-orange)'};
											            background: {isSamePerson(entry) ? (isActive(entry) ? 'var(--pt-green)' : 'var(--pt-bg-3)') : 'var(--pt-orange)'};"></div>

											<!-- Entry card -->
											<div class="p-3 transition-colors"
											     style="background: {isSamePerson(entry) ? 'var(--pt-bg-1)' : 'var(--pt-orange-tint)'};
											            border: 1px solid {isSamePerson(entry) ? 'var(--pt-border-muted)' : 'var(--pt-orange)'};
											            border-radius: 2px;">
												<div class="flex items-start justify-between gap-2">
													<div class="min-w-0">
														<p class="text-xs font-semibold leading-snug" style="color: var(--pt-text-primary);">{orgLabel(entry)}</p>
														{#if entry.person_name && entry.person_name !== selected?.name}
															<p class="text-xs mt-0.5 italic" style="color: var(--pt-text-muted);">as {entry.person_name}</p>
														{/if}
													</div>
													<div class="flex items-center gap-1 shrink-0 flex-wrap justify-end">
														{#if !isSamePerson(entry)}
															<span class="pt-tag pt-tag-orange">Different person?</span>
														{/if}
														{#if isLowConfidence(entry)}
															<span class="pt-tag pt-tag-violet">Low confidence</span>
														{/if}
														{#if isActive(entry)}
															<span class="pt-tag pt-tag-green">
																<span class="w-1.5 h-1.5 rounded-full" style="background: var(--pt-green);"></span>Active
															</span>
														{/if}
														<!-- Remove button: always visible on mobile (touch-friendly), hover-only on desktop -->
														<button onclick={() => removeEntry(entry)} title="Remove this entry"
														        class="sm:opacity-0 sm:group-hover:opacity-100 transition-opacity w-6 h-6 flex items-center justify-center"
														        style="border-radius: 2px; color: var(--pt-text-muted);"
														        onmouseover={(e) => { (e.currentTarget as HTMLElement).style.color = 'var(--pt-red)'; (e.currentTarget as HTMLElement).style.background = 'var(--pt-red-tint)'; }}
														        onmouseout={(e) => { (e.currentTarget as HTMLElement).style.color = 'var(--pt-text-muted)'; (e.currentTarget as HTMLElement).style.background = ''; }}>
															<svg class="w-3 h-3" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24">
																<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/>
															</svg>
														</button>
													</div>
												</div>
												{#if entry.rank}
													<p class="text-xs mt-0.5" style="color: var(--pt-text-secondary);">{entry.rank}</p>
												{/if}
												<div class="flex items-center gap-2 mt-1.5 flex-wrap">
													<span class="text-xs pt-data" style="color: var(--pt-text-muted);">
														{formatDate(entry.start_date)} → {formatDate(entry.end_date)}
													</span>
													{#if entry.tenure_days}
														<span class="text-xs px-1.5 py-0.5 pt-data"
														      style="color: var(--pt-text-secondary); background: var(--pt-bg-2); border-radius: 2px;">
															{formatDuration(entry.tenure_days)}
														</span>
													{/if}
												</div>
											</div>
										</li>
									{/each}
								</ul>
							</div>
						</div>

						<!-- ── Individual Profile ─────────── -->
						<div class="space-y-3">
							<h3 class="pt-label mb-3">Individual Profile</h3>
							<div class="pt-card space-y-3">
								{#if employmentSpan().from}
									<div>
										<p class="pt-label mb-0.5">Employment span</p>
										<p class="text-sm pt-data" style="color: var(--pt-text-primary);">{employmentSpan().from} — {employmentSpan().to}</p>
									</div>
								{/if}
								<div>
									<p class="pt-label mb-0.5">Roles shown</p>
									<p class="text-sm pt-data" style="color: var(--pt-text-primary);">
										{career.length} role{career.length !== 1 ? 's' : ''} across {distinctOrgs.length} org{distinctOrgs.length !== 1 ? 's' : ''}
									</p>
								</div>
							</div>
							<div class="pt-card">
								<p class="pt-label mb-2">Organisations</p>
								<ul class="space-y-1.5">
									{#each distinctOrgs as org}
										<li class="flex items-start gap-2">
											<div class="w-1 h-1 rounded-full shrink-0 mt-1.5" style="background: var(--pt-border);"></div>
											<p class="text-xs leading-snug" style="color: var(--pt-text-secondary);">{org}</p>
										</li>
									{/each}
								</ul>
							</div>
							{#if isDirty}
								<button onclick={reset} class="pt-button pt-button-outlined w-full">
									Reset to full timeline
								</button>
							{/if}
						</div>

					</div>
				{/if}
			</div>
		{/if}
	</section>
</div>
