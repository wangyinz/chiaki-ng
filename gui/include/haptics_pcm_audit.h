// SPDX-License-Identifier: LicenseRef-AGPL-3.0-only-OpenSSL
// Diagnostic only: this header never changes motor output or mixes channels.
#ifndef CHIAKI_HAPTICS_PCM_AUDIT_H
#define CHIAKI_HAPTICS_PCM_AUDIT_H

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <mutex>

namespace ChiakiHapticsAudit
{
struct Channel
{
	uint64_t absolute_sum = 0;
	uint64_t square_sum = 0;
	uint32_t peak = 0;
	size_t nonzero = 0;
};

struct Stats
{
	size_t frames = 0;
	std::array<Channel, 2> channel{};

	uint16_t Envelope(size_t i) const
	{
		if(!frames || i >= channel.size())
			return 0;
		return static_cast<uint16_t>(std::min<uint64_t>(
			65535, 2 * channel[i].absolute_sum / frames));
	}

	double Rms(size_t i) const
	{
		if(!frames || i >= channel.size())
			return 0.0;
		return std::sqrt(static_cast<double>(channel[i].square_sum) / frames);
	}
};

inline int32_t SignedLE16(const uint8_t *p)
{
	const uint32_t u = uint32_t(p[0]) | (uint32_t(p[1]) << 8);
	return u < 32768u ? static_cast<int32_t>(u)
		: static_cast<int32_t>(u) - 65536;
}

inline bool InspectS16LEStereo(const uint8_t *data, size_t size, Stats &out)
{
	out = {};
	if(!data || !size || size % 4 || size > 1024 * 1024)
		return false;

	out.frames = size / 4;
	for(size_t i = 0; i < out.frames; ++i)
	{
		for(size_t c = 0; c < 2; ++c)
		{
			const int32_t value = SignedLE16(data + i * 4 + c * 2);
			const uint32_t magnitude =
				static_cast<uint32_t>(value < 0 ? -value : value);
			auto &s = out.channel[c];
			s.absolute_sum += magnitude;
			s.square_sum += uint64_t(magnitude) * magnitude;
			s.peak = std::max(s.peak, magnitude);
			s.nonzero += magnitude != 0;
		}
	}
	return true;
}

enum class CaptureResult
{
	Disabled,
	Recorded,
	Started,
	Limit,
	Error,
};

class Capture
{
	std::mutex mutex;
	std::ofstream stream;
	bool attempted = false;
	bool finished = false;
	uint32_t index = 0;
	uint64_t total_bytes = 0;
	std::chrono::steady_clock::time_point start;

	static constexpr uint32_t MaxRecords = 4096;
	static constexpr uint32_t MaxRecordBytes = 4096;
	static constexpr uint64_t MaxPayloadBytes = 512 * 1024;

	void PutLE(uint64_t value, size_t count)
	{
		char bytes[8]{};
		for(size_t i = 0; i < count; ++i)
			bytes[i] = static_cast<char>((value >> (8 * i)) & 0xff);
		stream.write(bytes, static_cast<std::streamsize>(count));
	}

public:
	CaptureResult Record(const uint8_t *data, size_t size) noexcept
	{
		try
		{
			std::lock_guard<std::mutex> lock(mutex);
			if(finished)
				return CaptureResult::Disabled;

			bool opened_now = false;
			if(!attempted)
			{
				attempted = true;
				const char *name = std::getenv("CHIAKI_HAPTICS_CAPTURE");
				if(!name || !*name)
				{
					finished = true;
					return CaptureResult::Disabled;
				}

				const std::filesystem::path path = std::filesystem::u8path(name);
				if(std::filesystem::exists(path))
				{
					finished = true;
					return CaptureResult::Error;
				}

				stream.open(path, std::ios::binary | std::ios::out);
				if(!stream)
				{
					finished = true;
					return CaptureResult::Error;
				}

				stream.write("CHPCM001", 8);
				start = std::chrono::steady_clock::now();
				opened_now = true;
			}

			if(!data || !size || size > MaxRecordBytes)
				return opened_now ? CaptureResult::Started : CaptureResult::Recorded;

			if(index >= MaxRecords || total_bytes + size > MaxPayloadBytes)
			{
				stream.close();
				finished = true;
				return CaptureResult::Limit;
			}

			const auto now = std::chrono::steady_clock::now();
			const auto wall = std::chrono::system_clock::now().time_since_epoch();
			const uint64_t elapsed_us = static_cast<uint64_t>(
				std::chrono::duration_cast<std::chrono::microseconds>(now - start).count());
			const uint64_t epoch_us = static_cast<uint64_t>(
				std::chrono::duration_cast<std::chrono::microseconds>(wall).count());

			PutLE(index++, 4);
			PutLE(epoch_us, 8);
			PutLE(elapsed_us, 8);
			PutLE(size, 4);
			stream.write(reinterpret_cast<const char *>(data),
				static_cast<std::streamsize>(size));
			total_bytes += size;

			if(opened_now || index % 100 == 0)
				stream.flush();

			if(!stream)
			{
				stream.close();
				finished = true;
				return CaptureResult::Error;
			}
			return opened_now ? CaptureResult::Started : CaptureResult::Recorded;
		}
		catch(...)
		{
			try
			{
				std::lock_guard<std::mutex> lock(mutex);
				if(stream.is_open())
					stream.close();
				finished = true;
			}
			catch(...)
			{
			}
			return CaptureResult::Error;
		}
	}
};
} // namespace ChiakiHapticsAudit

#endif // CHIAKI_HAPTICS_PCM_AUDIT_H
