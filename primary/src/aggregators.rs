// Copyright(C) Facebook, Inc. and its affiliates.
use crate::error::{DagError, DagResult};
use crate::messages::{
    merge_author_bitmaps, set_author_bit, Certificate, Header, ProposalParents, Vote,
};
use crate::primary::Round;
use config::{Committee, Stake};
use crypto::Hash as _;
use crypto::{Digest, PublicKey, Signature};
use log::debug;
use std::collections::HashSet;
use std::time::{Duration, Instant};

/// Aggregates votes for a particular header into a certificate.
pub struct VotesAggregator {
    weight: Stake,
    votes: Vec<(PublicKey, Signature)>,
    used: HashSet<PublicKey>,
}

impl VotesAggregator {
    pub fn new() -> Self {
        Self {
            weight: 0,
            votes: Vec::new(),
            used: HashSet::new(),
        }
    }

    pub fn append(
        &mut self,
        vote: Vote,
        committee: &Committee,
        header: &Header,
    ) -> DagResult<Option<Certificate>> {
        let author = vote.author;

        // Ensure it is the first time this authority votes.
        ensure!(self.used.insert(author), DagError::AuthorityReuse(author));

        self.votes.push((author, vote.signature));
        self.weight += committee.stake(&author);
        debug!(
            "VotesAggregator: received vote for header {} (round {}), votes in this round for this header: {} (weight={})",
            header.id,
            header.round,
            self.votes.len(),
            self.weight
        );
        if self.weight >= committee.quorum_threshold() {
            self.weight = 0; // Ensures quorum is only reached once.
            return Ok(Some(Certificate {
                header: header.clone(),
                votes: self.votes.clone(),
            }));
        }
        Ok(None)
    }
}

/// Aggregate certificates and check if we reach a quorum.
pub struct CertificatesAggregator {
    expected_round: Round,
    weight: Stake,
    certificates: Vec<Digest>,
    weak_certificates: Vec<Digest>,
    used: HashSet<PublicKey>,
    has_quorum: bool,
    /// Wait for several seconds after meeting the condition
    quorum_reached_time: Option<Instant>,
    wait_duration: Duration,
    /// Incremental union of parents' solid-step summaries for the proposal round.
    solid_step_union: HashSet<Digest>,
    /// Incremental union of parents' solid-wave summaries for the proposal round.
    solid_wave_union: HashSet<Digest>,
    /// Last computed union of parents' solid_step_vertices_merged on solid rounds
    /// (for debug / final_dag display).
    last_union_set: Option<Vec<Digest>>,
    /// The round whose reachable authors are tracked for the proposal round.
    back_link_target_round: Round,
    /// Bitmap over committee order for tracked-round authors reachable through
    /// the current parent set.
    back_link_author_bitmap: Vec<u8>,
}

impl CertificatesAggregator {
    pub fn new(expected_round: Round) -> Self {
        Self {
            expected_round,
            weight: 0,
            certificates: Vec::new(),
            weak_certificates: Vec::new(),
            used: HashSet::new(),
            has_quorum: false,
            quorum_reached_time: None,
            wait_duration: Duration::from_millis(20),
            solid_step_union: HashSet::new(),
            solid_wave_union: HashSet::new(),
            last_union_set: None,
            back_link_target_round: 0,
            back_link_author_bitmap: Vec::new(),
        }
    }

    /// Returns the last computed union of parents' solid_step_vertices_merged
    /// (when advancing to a solid round). Used by core to resolve digests to
    /// [round, node_id] for debug and final_dag.
    pub fn last_solid_step_union_digests(&self) -> Option<&[Digest]> {
        self.last_union_set.as_deref()
    }

    fn extend_step_union(&mut self, certificate: &Certificate) {
        if certificate.header.solid_step_vertices_merged.is_empty() {
            self.solid_step_union
                .extend(certificate.header.solid_step_vertices.iter().cloned());
        } else {
            self.solid_step_union
                .extend(certificate.header.solid_step_vertices_merged.iter().cloned());
        }
    }

    fn extend_wave_union(&mut self, certificate: &Certificate) {
        if certificate.header.solid_wave_vertices_merged.is_empty() {
            self.solid_wave_union
                .extend(certificate.header.solid_wave_vertices.iter().cloned());
        } else {
            self.solid_wave_union
                .extend(certificate.header.solid_wave_vertices_merged.iter().cloned());
        }
    }

    fn extend_back_link_bitmap(
        &mut self,
        certificate: &Certificate,
        committee: &Committee,
        target_round: Round,
    ) {
        if target_round == 0 {
            return;
        }
        if self.back_link_author_bitmap.is_empty() {
            self.back_link_author_bitmap = vec![0; committee.authority_bitmap_len()];
        }
        if certificate.round() == target_round {
            if let Some(index) = committee.authority_index(&certificate.origin()) {
                set_author_bit(&mut self.back_link_author_bitmap, index);
            }
        }
        if certificate.header.wave_back_link_target_round == target_round {
            merge_author_bitmaps(
                &mut self.back_link_author_bitmap,
                &certificate.header.wave_back_link_author_bitmap,
            );
        }
    }

    pub fn append(
        &mut self,
        certificate: Certificate,
        committee: &Committee,
        require_core: bool,
    ) -> DagResult<Option<ProposalParents>> {
        let origin = certificate.origin();

        // Ensure it is the first time this authority votes as a strong edge.
        if certificate.round() == self.expected_round && !self.used.insert(origin) {
            return Ok(None);
        }

        // Accept strong parents from the previous round. Weak parents always
        // remain available inside the current solid step; optionally they may
        // extend into earlier solid steps that still lie inside the current
        // solid-wave window.
        let current_round = self.expected_round + 1;
        let regular_weak_start = committee.solid_step_parent_start(current_round);
        let cross_step_weak_start = committee.cross_step_weak_parent_start(current_round);
        let back_link_target_round = committee
            .wave_back_link_tracking_round(current_round)
            .unwrap_or(0);

        // Add the certificate to the appropriate list.
        if certificate.round() == self.expected_round {
            self.certificates.push(certificate.digest());
            self.extend_step_union(&certificate);
            self.extend_wave_union(&certificate);
            self.back_link_target_round = back_link_target_round;
            self.extend_back_link_bitmap(&certificate, committee, back_link_target_round);
            self.weight += committee.stake(&origin);
        } else if certificate.round() >= regular_weak_start
            && certificate.round() < self.expected_round
        {
            self.certificates.push(certificate.digest());
            self.weak_certificates.push(certificate.digest());
            self.extend_step_union(&certificate);
            self.extend_wave_union(&certificate);
            self.back_link_target_round = back_link_target_round;
            self.extend_back_link_bitmap(&certificate, committee, back_link_target_round);
        } else if certificate.round() >= cross_step_weak_start
            && certificate.round() < regular_weak_start
        {
            self.certificates.push(certificate.digest());
            self.weak_certificates.push(certificate.digest());
            self.extend_wave_union(&certificate);
            self.back_link_target_round = back_link_target_round;
            self.extend_back_link_bitmap(&certificate, committee, back_link_target_round);
        } else {
            return Ok(None);
        }
        debug!(
            "Current round: {}, regular weak range: [{}..={}), cross-step weak range: [{}..={})",
            current_round,
            regular_weak_start,
            self.expected_round,
            cross_step_weak_start,
            regular_weak_start
        );

        let threshold = committee.processing_threshold(current_round);
        let is_solid_step = committee.is_solid_step(current_round);
        debug!(
            "Advance to round {}: require weight >= {}, solid_step={})",
            current_round, threshold, is_solid_step
        );
        if is_solid_step {
            self.last_union_set = Some(self.solid_step_union.iter().cloned().collect());
            self.has_quorum =
                self.solid_step_union.len()
                    >= committee.processing_threshold(current_round) as usize;
            debug!(
                "Current round: {}, The number of merged solid-step vertices is {}",
                current_round,
                self.solid_step_union.len()
            );
        } else {
            self.has_quorum = self.weight >= committee.processing_threshold(current_round);
            debug!(
                "Current round: {}, The weight is {}, self_has_quorum: {}",
                current_round, self.weight, self.has_quorum
            );
        }
        // Modify processing condition
        // if self.expected_round % committee.solid_step_length() as u64 == 1 && self.expected_round > 1 {
        //     if self.certificates..solid_step_vertices.len() >= committee.processing_threshold(self.expected_round as u64) {
        //         self.has_quorum = true;
        //     }
        // } else {
        //     if self.weight >= committee.processing_threshold(self.expected_round as u64) {
        //         self.has_quorum = true;
        //     }
        // }

        // A count/union threshold cannot substitute for a missing mandatory core author.
        // Only certificates from the immediately preceding round populate `used`.
        if require_core {
            self.has_quorum &= committee
                .selective_attack_core_members()
                .all(|author| self.used.contains(author));
        }

        if self.has_quorum {
            if self.quorum_reached_time.is_none() {
                self.quorum_reached_time = Some(Instant::now());
            }
            let mut proposal_parents = ProposalParents::from(self.certificates.clone());
            proposal_parents.solid_step_union = self.solid_step_union.clone();
            proposal_parents.solid_wave_union = self.solid_wave_union.clone();
            proposal_parents.wave_back_link_target_round = self.back_link_target_round;
            proposal_parents.wave_back_link_author_bitmap = self.back_link_author_bitmap.clone();
            // if self.quorum_reached_time.unwrap().elapsed() >= self.wait_duration || self.weight >= committee.max_threshold() {
            return Ok(Some(proposal_parents));
            // }
        }
        Ok(None)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::common::{attack_committee, certificate, headers};

    fn ordered_certificates(round: Round) -> Vec<Certificate> {
        let mut headers = headers();
        headers.sort_by_key(|header| header.author);
        headers
            .into_iter()
            .map(|mut header| {
                header.round = round;
                header.solid_step_vertices = [header.id.clone()].iter().cloned().collect();
                certificate(&header)
            })
            .collect()
    }

    #[test]
    fn waits_for_every_core_author_even_after_reference_is_met() {
        let mut committee = attack_committee(3);
        committee.reference = 2;
        let certificates = ordered_certificates(1);
        let mut aggregator = CertificatesAggregator::new(1);
        for index in [0, 2, 3] {
            assert!(aggregator
                .append(certificates[index].clone(), &committee, true)
                .unwrap()
                .is_none());
        }
        assert!(aggregator
            .append(certificates[1].clone(), &committee, true)
            .unwrap()
            .is_some());
    }

    #[test]
    fn weak_core_certificate_does_not_unlock_solid_round() {
        let committee = attack_committee(3);
        let certificates = ordered_certificates(2);
        let mut aggregator = CertificatesAggregator::new(2);
        for index in [0, 2, 3] {
            assert!(aggregator
                .append(certificates[index].clone(), &committee, true)
                .unwrap()
                .is_none());
        }
        let weak_core = ordered_certificates(1)[1].clone();
        assert!(aggregator
            .append(weak_core, &committee, true)
            .unwrap()
            .is_none());
        assert!(aggregator
            .append(certificates[1].clone(), &committee, true)
            .unwrap()
            .is_some());
    }

    #[test]
    fn core_does_not_replace_original_reference_threshold() {
        let mut committee = attack_committee(4);
        committee.reference = 4;
        let certificates = ordered_certificates(1);
        let mut aggregator = CertificatesAggregator::new(1);
        for index in [0, 1, 2] {
            assert!(aggregator
                .append(certificates[index].clone(), &committee, true)
                .unwrap()
                .is_none());
        }
        assert!(aggregator
            .append(certificates[3].clone(), &committee, true)
            .unwrap()
            .is_some());
    }

    #[test]
    fn outside_attack_window_original_threshold_is_sufficient() {
        let mut committee = attack_committee(3);
        committee.reference = 2;
        let certificates = ordered_certificates(1);
        let mut aggregator = CertificatesAggregator::new(1);
        assert!(aggregator
            .append(certificates[0].clone(), &committee, false)
            .unwrap()
            .is_none());
        assert!(aggregator
            .append(certificates[2].clone(), &committee, false)
            .unwrap()
            .is_some());
    }

    #[test]
    fn ending_attack_releases_core_requirement() {
        let mut committee = attack_committee(3);
        committee.reference = 2;
        let certificates = ordered_certificates(1);
        let mut aggregator = CertificatesAggregator::new(1);
        for index in [0, 2] {
            assert!(aggregator
                .append(certificates[index].clone(), &committee, true)
                .unwrap()
                .is_none());
        }
        assert!(aggregator
            .append(certificates[3].clone(), &committee, false)
            .unwrap()
            .is_some());
    }
}
