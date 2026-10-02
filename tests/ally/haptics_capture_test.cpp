// SPDX-License-Identifier: LicenseRef-AGPL-3.0-only-OpenSSL
#include "haptics_pcm_audit.h"

#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <iostream>

int main()
{
	const char *path = std::getenv("CHIAKI_HAPTICS_CAPTURE");
	assert(path && *path);
	assert(!std::filesystem::exists(std::filesystem::u8path(path)));

	uint8_t pcm[120]{};
	for(unsigned i = 0; i < 30; ++i)
	{
		pcm[i * 4] = 0x34;
		pcm[i * 4 + 1] = 0x12;
		pcm[i * 4 + 2] = 0x78;
		pcm[i * 4 + 3] = 0x56;
	}

	ChiakiHapticsAudit::Capture capture;
	assert(capture.Record(pcm, sizeof(pcm)) == ChiakiHapticsAudit::CaptureResult::Started);
	for(unsigned i = 1; i < 4096; ++i)
		assert(capture.Record(pcm, sizeof(pcm)) == ChiakiHapticsAudit::CaptureResult::Recorded);
	assert(capture.Record(pcm, sizeof(pcm)) == ChiakiHapticsAudit::CaptureResult::Limit);
	assert(capture.Record(pcm, sizeof(pcm)) == ChiakiHapticsAudit::CaptureResult::Disabled);
	assert(std::filesystem::file_size(std::filesystem::u8path(path)) ==
		8u + 4096u * (24u + sizeof(pcm)));

	std::cout << "PASS: bounded raw haptics capture\n";
	return 0;
}
