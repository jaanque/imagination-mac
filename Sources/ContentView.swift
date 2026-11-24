import SwiftUI

#if os(iOS)
import UIKit
#endif

struct ContentView: View {
    @State private var buildPulseCount = 0
    @State private var isAnimating = false

    private var platformName: String {
        #if os(iOS)
        return UIDevice.current.systemName
        #elseif os(macOS)
        return "macOS"
        #else
        return "Apple OS"
        #endif
    }

    private var osVersion: String {
        #if os(iOS)
        return UIDevice.current.systemVersion
        #elseif os(macOS)
        let version = ProcessInfo.processInfo.operatingSystemVersion
        return "\(version.majorVersion).\(version.minorVersion).\(version.patchVersion)"
        #else
        return ProcessInfo.processInfo.operatingSystemVersionString
        #endif
    }

    private var deviceModel: String {
        #if os(iOS)
        return UIDevice.current.model
        #elseif os(macOS)
        return "Mac"
        #else
        return "Unknown"
        #endif
    }

    var body: some View {
        VStack(spacing: 24) {
            Spacer()

            ZStack {
                Circle()
                    .fill(Color.accentColor.opacity(0.12))
                    .frame(width: 96, height: 96)
                    .scaleEffect(isAnimating ? 1.08 : 1.0)

                Image(systemName: "checkmark.icloud.fill")
                    .font(.system(size: 44, weight: .semibold))
                    .foregroundStyle(Color.accentColor)
                    .symbolEffect(.bounce, value: buildPulseCount)
            }

            VStack(spacing: 8) {
                Text("Cloud Build Succeeded")
                    .font(.title2.weight(.bold))

                Text("Compiled with GitHub Actions without a local Mac.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal)
            }

            VStack(spacing: 12) {
                InfoRow(label: "Platform", value: platformName)
                Divider()
                InfoRow(label: "OS Version", value: osVersion)
                Divider()
                InfoRow(label: "Device", value: deviceModel)
            }
            .padding(16)
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .strokeBorder(.quaternary, lineWidth: 1)
            )
            .padding(.horizontal, 24)

            Button {
                withAnimation(.spring(response: 0.35, dampingFraction: 0.6)) {
                    buildPulseCount += 1
                    isAnimating = true
                }
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) {
                    withAnimation(.easeOut(duration: 0.2)) {
                        isAnimating = false
                    }
                }
            } label: {
                HStack(spacing: 8) {
                    Image(systemName: "sparkles")
                    Text(buildPulseCount == 0 ? "Test Interactive UI" : "Interactions: \(buildPulseCount)")
                }
                .font(.headline)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 12)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .padding(.horizontal, 24)

            Spacer()

            Text("Edit Sources/ContentView.swift to customize this view.")
                .font(.footnote)
                .foregroundStyle(.tertiary)
                .padding(.bottom, 16)
        }
        .frame(minWidth: 340, minHeight: 500)
    }
}

private struct InfoRow: View {
    let label: String
    let value: String

    var body: some View {
        HStack {
            Text(label)
                .foregroundStyle(.secondary)
            Spacer()
            Text(value)
                .fontWeight(.medium)
                .monospacedDigit()
        }
        .font(.subheadline)
    }
}

#Preview {
    ContentView()
}
