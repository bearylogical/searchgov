<script lang="ts">
	import { page } from '$app/state';
</script>

<div class="flex flex-col items-center justify-center min-h-[50vh] gap-4 text-center">
	<p class="text-6xl font-bold text-gray-200">{page.status}</p>
	<p class="text-xl font-semibold text-gray-700">{page.error?.message ?? 'Something went wrong'}</p>
	<a href="/" class="text-sm text-blue-600 hover:text-blue-800 mt-2">← Back to home</a>
</div>
