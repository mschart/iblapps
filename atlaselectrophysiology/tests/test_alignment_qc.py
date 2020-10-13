import unittest
from oneibl.one import ONE
from ibllib.atlas import AllenAtlas
from atlaselectrophysiology.load_data import LoadData
from ibllib.pipes.ephys_alignment import EphysAlignment
from ibllib.pipes.misc import create_alyx_probe_insertions
from ibllib.qc.alignment_qc import AlignmentQC
from ibllib.pipes.histology import register_track
from pathlib import Path
import numpy as np
import copy

EPHYS_SESSION = 'b1c968ad-4874-468d-b2e4-5ffa9b9964e9'
one = ONE(username='test_user', password='TapetesBloc18',
          base_url='https://test.alyx.internationalbrainlab.org')
brain_atlas = AllenAtlas(25)


class TestProbeInsertion(unittest.TestCase):

    def test_creation(self):
        probe = ['probe00', 'probe01']
        create_alyx_probe_insertions(session_path=EPHYS_SESSION, model='3B2', labels=probe,
                                     one=one, force=True)
        insertion = one.alyx.rest('insertions', 'list', session=EPHYS_SESSION)
        assert(len(insertion) == 2)
        assert (insertion[0]['json']['qc'] == 'NOT_SET')
        assert (len(insertion[0]['json']['extended_qc']) == 0)


class TestHistologyQc(unittest.TestCase):

    def test_session_creation(self):
        pass

    def test_probe_qc(self):
        pass


class TestTracingQc(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.probe00_id = one.alyx.rest('insertions', 'list', session=EPHYS_SESSION,
                                       name='probe00')[0]['id']
        cls.probe01_id = one.alyx.rest('insertions', 'list', session=EPHYS_SESSION,
                                       name='probe01')[0]['id']
        data = np.load(Path(Path(__file__).parent.
                            joinpath('fixtures', 'data_alignmentqc_gui.npz')), allow_pickle=True)
        cls.xyz_picks = data['xyz_picks']

    def test_tracing_exists(self):
        register_track(self.probe00_id, picks=self.xyz_picks, one=one, overwrite=True,
                       channels=False)
        insertion = one.alyx.rest('insertions', 'read', id=self.probe00_id)

        assert (insertion['json']['qc'] == 'NOT_SET')
        assert (insertion['json']['extended_qc']['_tracing_exists'] == 1)

    def test_tracing_not_exists(self):
        register_track(self.probe01_id, picks=None, one=one, overwrite=True,
                       channels=False)
        insertion = one.alyx.rest('insertions', 'read', id=self.probe01_id)
        assert (insertion['json']['qc'] == 'CRITICAL')
        assert (insertion['json']['extended_qc']['_tracing_exists'] == 0)

    @classmethod
    def tearDownClass(cls) -> None:
        one.alyx.rest('insertions', 'delete', id=cls.probe01_id)
        one.alyx.rest('insertions', 'delete', id=cls.probe00_id)


class TestsAlignmentQcGUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        probe = ['probe00']
        create_alyx_probe_insertions(session_path=EPHYS_SESSION, model='3B2', labels=probe,
                                     one=one, force=True)
        cls.probe_id = one.alyx.rest('insertions', 'list', session=EPHYS_SESSION,
                                     name='probe00')[0]['id']
        data = np.load(Path(Path(__file__).parent.
                            joinpath('fixtures', 'data_alignmentqc_gui.npz')), allow_pickle=True)
        cls.xyz_picks = data['xyz_picks']
        cls.alignments = data['alignments'].tolist()
        cls.cluster_chns = data['cluster_chns']
        register_track(cls.probe_id, picks=cls.xyz_picks, one=one, overwrite=True,
                       channels=False)

    def setUp(self) -> None:
        self.resolved_key = '2020-09-14T15:44:56_nate'
        self.ld = LoadData(one=one, brain_atlas=brain_atlas, testing=True, probe_id=self.probe_id)
        _ = self.ld.get_xyzpicks()
        self.ld.cluster_chns = self.cluster_chns
        _ = self.ld.get_previous_alignments()
        _ = self.ld.get_starting_alignment(0)
        self.ephysalign = EphysAlignment(self.ld.xyz_picks, self.ld.chn_depths,
                                         brain_atlas=self.ld.brain_atlas)
        traj = one.alyx.rest('trajectories', 'list', probe_id=self.probe_id,
                             provenance='Ephys aligned histology track')
        if traj:
            self.prev_traj_id = traj[0]['id']

    def test_01_no_alignment(self):

        prev_align = self.ld.get_previous_alignments()
        assert (len(prev_align) == 1)
        assert (prev_align[0] == 'original')
        feature, track = self.ld.get_starting_alignment(0)
        assert (not feature)
        assert (not track)
        assert (not self.ld.alignments)
        assert (self.ld.resolved == 0)

    def test_02_one_alignment(self):
        key = '2020-07-26T17:06:58_alejandro'
        feature = self.alignments[key][0]
        track = self.alignments[key][1]
        xyz_channels = self.ephysalign.get_channel_locations(feature, track)
        self.ld.upload_data(xyz_channels, channels=False)
        self.ld.update_alignments(np.array(feature), np.array(track), key_info=key)
        _ = self.ld.get_previous_alignments()
        _ = self.ld.get_starting_alignment(0)
        assert (self.ld.current_align == key)

        traj = one.alyx.rest('trajectories', 'list', probe_id=self.probe_id,
                             provenance='Ephys aligned histology track')
        assert (sorted(list(traj[0]['json'].keys()), reverse=True)[0] == key)
        assert (len(traj[0]['json']) == 1)

        self.ld.update_qc()
        insertion = one.alyx.rest('insertions', 'read', id=self.probe_id)
        assert (insertion['json']['extended_qc']['_alignment_number'] == 1)
        assert (insertion['json']['extended_qc']['_alignment_stored'] == key)
        assert (insertion['json']['qc'] == 'NOT_SET')
        assert (self.ld.resolved == 0)

    def test_03_same_user(self):
        key = '2020-08-26T17:06:58_alejandro'
        feature = self.alignments[key][0]
        track = self.alignments[key][1]
        xyz_channels = self.ephysalign.get_channel_locations(feature, track)
        self.ld.upload_data(xyz_channels, channels=False)
        self.ld.update_alignments(np.array(feature), np.array(track), key_info=key)
        _ = self.ld.get_previous_alignments()
        _ = self.ld.get_starting_alignment(0)
        assert (self.ld.current_align == key)

        traj = one.alyx.rest('trajectories', 'list', probe_id=self.probe_id,
                             provenance='Ephys aligned histology track')
        traj_id = traj[0]['id']
        assert (sorted(list(traj[0]['json'].keys()), reverse=True)[0] == key)
        assert (len(traj[0]['json']) == 1)
        assert (traj_id != self.prev_traj_id)

        self.ld.update_qc()
        insertion = one.alyx.rest('insertions', 'read', id=self.probe_id)
        assert (insertion['json']['extended_qc']['_alignment_number'] == 1)
        assert (insertion['json']['extended_qc']['_alignment_stored'] == key)
        assert (insertion['json']['qc'] == 'NOT_SET')
        assert (self.ld.resolved == 0)

    def test_04_two_alignments(self):
        key = '2020-09-14T15:42:22_guido'
        feature = self.alignments[key][0]
        track = self.alignments[key][1]
        xyz_channels = self.ephysalign.get_channel_locations(feature, track)
        self.ld.upload_data(xyz_channels, channels=False)
        self.ld.update_alignments(np.array(feature), np.array(track), key_info=key)
        _ = self.ld.get_previous_alignments()
        _ = self.ld.get_starting_alignment(0)

        assert (self.ld.current_align == key)

        traj = one.alyx.rest('trajectories', 'list', probe_id=self.probe_id,
                             provenance='Ephys aligned histology track')
        traj_id = traj[0]['id']
        assert (sorted(list(traj[0]['json'].keys()), reverse=True)[0] == key)
        assert (len(traj[0]['json']) == 2)
        assert (traj_id != self.prev_traj_id)
        # Also assert all the keys match

        self.ld.update_qc()
        insertion = one.alyx.rest('insertions', 'read', id=self.probe_id)
        assert (insertion['json']['qc'] == 'WARNING')
        assert (insertion['json']['extended_qc']['_alignment_number'] == 2)
        assert (insertion['json']['extended_qc']['_alignment_stored'] == key)
        assert (insertion['json']['extended_qc']['_alignment_resolved'] == 0)
        assert (insertion['json']['extended_qc']['_alignment_qc'] < 0.8)
        assert (self.ld.resolved == 0)

    def test_05_three_alignments(self):

        key = '2020-09-14T15:44:56_nate'
        feature = self.alignments[key][0]
        track = self.alignments[key][1]
        xyz_channels = self.ephysalign.get_channel_locations(feature, track)
        self.ld.upload_data(xyz_channels, channels=False)
        self.ld.update_alignments(np.array(feature), np.array(track), key_info=key)
        _ = self.ld.get_previous_alignments()
        _ = self.ld.get_starting_alignment(0)

        assert (self.ld.current_align == key)

        traj = one.alyx.rest('trajectories', 'list', probe_id=self.probe_id,
                             provenance='Ephys aligned histology track')
        traj_id = traj[0]['id']
        assert (len(traj[0]['json']) == 3)
        assert (sorted(list(traj[0]['json'].keys()), reverse=True)[0] == key)
        assert (traj_id != self.prev_traj_id)

        self.ld.update_qc()
        insertion = one.alyx.rest('insertions', 'read', id=self.probe_id)
        assert (insertion['json']['qc'] == 'PASS')
        assert (insertion['json']['extended_qc']['_alignment_number'] == 3)
        assert (insertion['json']['extended_qc']['_alignment_stored'] == key)
        assert (insertion['json']['extended_qc']['_alignment_resolved'] == 1)
        assert (insertion['json']['extended_qc']['_alignment_qc'] > 0.8)
        assert(self.ld.resolved == 1)

    def test_06_new_user_after_resolved(self):
        key = '2020-09-16T15:44:56_mayo'
        feature = self.alignments[key][0]
        track = self.alignments[key][1]
        xyz_channels = self.ephysalign.get_channel_locations(feature, track)
        self.ld.upload_data(xyz_channels, channels=False)
        self.ld.update_alignments(np.array(feature), np.array(track), key_info=key)
        _ = self.ld.get_previous_alignments()
        _ = self.ld.get_starting_alignment(0)

        assert (self.ld.current_align == key)

        traj = one.alyx.rest('trajectories', 'list', probe_id=self.probe_id,
                             provenance='Ephys aligned histology track')
        traj_id = traj[0]['id']
        assert (len(traj[0]['json']) == 4)
        assert (sorted(list(traj[0]['json'].keys()), reverse=True)[0] == key)
        assert (traj_id == self.prev_traj_id)

        self.ld.update_qc()
        insertion = one.alyx.rest('insertions', 'read', id=self.probe_id)
        assert (insertion['json']['qc'] == 'PASS')
        assert (insertion['json']['extended_qc']['_alignment_number'] == 4)
        assert (insertion['json']['extended_qc']['_alignment_stored'] == self.resolved_key)
        assert (insertion['json']['extended_qc']['_alignment_resolved'] == 1)
        assert (insertion['json']['extended_qc']['_alignment_qc'] > 0.8)
        assert (self.ld.resolved == 1)

    def test_07_same_user_after_resolved(self):
        key = '2020-10-14T15:44:56_nate'
        feature = self.alignments[key][0]
        track = self.alignments[key][1]
        xyz_channels = self.ephysalign.get_channel_locations(feature, track)
        self.ld.upload_data(xyz_channels, channels=False)
        self.ld.update_alignments(np.array(feature), np.array(track), key_info=key)
        _ = self.ld.get_previous_alignments()
        _ = self.ld.get_starting_alignment(0)

        assert (self.ld.current_align == key)

        traj = one.alyx.rest('trajectories', 'list', probe_id=self.probe_id,
                             provenance='Ephys aligned histology track')
        traj_id = traj[0]['id']
        assert (sorted(list(traj[0]['json'].keys()), reverse=True)[0] == key)
        assert (len(traj[0]['json']) == 5)
        assert (traj_id == self.prev_traj_id)

        self.ld.update_qc()
        insertion = one.alyx.rest('insertions', 'read', id=self.probe_id)
        assert (insertion['json']['qc'] == 'PASS')
        assert (insertion['json']['extended_qc']['_alignment_number'] == 5)
        assert (insertion['json']['extended_qc']['_alignment_stored'] == self.resolved_key)
        assert (insertion['json']['extended_qc']['_alignment_resolved'] == 1)
        assert (insertion['json']['extended_qc']['_alignment_qc'] > 0.8)
        assert (self.ld.resolved == 1)

    @classmethod
    def tearDownClass(cls) -> None:
        one.alyx.rest('insertions', 'delete', id=cls.probe_id)


class TestAlignmentQcExisting(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        data = np.load(Path(Path(__file__).parent.
                            joinpath('fixtures', 'data_alignmentqc_existing.npz')),
                       allow_pickle=True)
        # data = np.load('data_alignmentqc_existing.npz', allow_pickle=True)
        cls.xyz_picks = data['xyz_picks'].tolist()
        cls.alignments = data['alignments'].tolist()
        # Manipulate so one alignment disagrees
        cls.alignments['2020-06-26T16:40:14_Karolina_Socha'][1] = \
            list(np.array(cls.alignments['2020-06-26T16:40:14_Karolina_Socha'][1]) + 0.0001)
        cls.cluster_chns = data['cluster_chns']
        insertion = data['insertion'].tolist()
        insertion['json'] = {'xyz_picks': cls.xyz_picks}
        probe_insertion = one.alyx.rest('insertions', 'create', data=insertion)
        cls.probe_id = probe_insertion['id']
        cls.trajectory = data['trajectory'].tolist()
        cls.trajectory.update({'probe_insertion': cls.probe_id})

    def setUp(self):
        traj = one.alyx.rest('trajectories', 'list', probe_id=self.probe_id,
                             provenance='Ephys aligned histology track')
        if traj:
            self.prev_traj_id = traj[0]['id']

    def test_01_alignments_disagree(self):
        alignments = {'2020-06-26T16:40:14_Karolina_Socha':
                      self.alignments['2020-06-26T16:40:14_Karolina_Socha'],
                      '2020-06-12T00:39:15_nate': self.alignments['2020-06-12T00:39:15_nate']}
        trajectory = copy.deepcopy(self.trajectory)
        trajectory.update({'json': alignments})
        traj = one.alyx.rest('trajectories', 'create', data=trajectory)
        traj_id = traj['id']
        align_qc = AlignmentQC(self.probe_id, one=one, brain_atlas=brain_atlas, channels=False)
        insertion = one.alyx.rest('insertions', 'read', id=self.probe_id)
        # Make sure the qc fields have been added to the insertion object
        assert(insertion['json']['qc'] == 'NOT_SET')
        assert(len(insertion['json']['extended_qc']) == 0)
        align_qc.load_data(prev_alignments=traj['json'], xyz_picks=np.array(self.xyz_picks) / 1e6,
                           cluster_chns=self.cluster_chns)
        align_qc.run(update=True, upload=True)
        insertion = one.alyx.rest('insertions', 'read', id=self.probe_id)
        assert (insertion['json']['qc'] == 'WARNING')
        assert (insertion['json']['extended_qc']['_alignment_number'] == 2)
        assert (insertion['json']['extended_qc']['_alignment_stored'] ==
                '2020-06-26T16:40:14_Karolina_Socha')
        assert (insertion['json']['extended_qc']['_alignment_resolved'] == 0)
        assert (insertion['json']['extended_qc']['_alignment_qc'] < 0.8)
        traj = one.alyx.rest('trajectories', 'list', probe_id=self.probe_id,
                             provenance='Ephys aligned histology track')
        assert(traj_id == traj[0]['id'])

    def test_02_alignments_agree(self):
        alignments = {'2020-06-19T10:52:36_noam.roth':
                      self.alignments['2020-06-19T10:52:36_noam.roth'],
                      '2020-06-12T00:39:15_nate': self.alignments['2020-06-12T00:39:15_nate']}
        trajectory = copy.deepcopy(self.trajectory)
        trajectory.update({'json': alignments})
        traj = one.alyx.rest('trajectories', 'update', id=self.prev_traj_id, data=trajectory)
        assert(self.prev_traj_id == traj['id'])
        align_qc = AlignmentQC(self.probe_id, one=one, brain_atlas=brain_atlas, channels=False)
        align_qc.load_data(prev_alignments=traj['json'], xyz_picks=np.array(self.xyz_picks) / 1e6,
                           cluster_chns=self.cluster_chns)
        align_qc.run(update=True, upload=True)
        insertion = one.alyx.rest('insertions', 'read', id=self.probe_id)
        assert (insertion['json']['qc'] == 'PASS')
        assert (insertion['json']['extended_qc']['_alignment_number'] == 2)
        assert (insertion['json']['extended_qc']['_alignment_stored'] ==
                '2020-06-19T10:52:36_noam.roth')
        assert (insertion['json']['extended_qc']['_alignment_resolved'] == 1)
        assert (insertion['json']['extended_qc']['_alignment_qc'] > 0.8)
        traj = one.alyx.rest('trajectories', 'list', probe_id=self.probe_id,
                             provenance='Ephys aligned histology track')
        assert(self.prev_traj_id == traj[0]['id'])

    def test_03_not_latest_alignments_agree(self):
        alignments = copy.deepcopy(self.alignments)
        trajectory = copy.deepcopy(self.trajectory)
        trajectory.update({'json': alignments})
        traj = one.alyx.rest('trajectories', 'update', id=self.prev_traj_id, data=trajectory)
        assert(self.prev_traj_id == traj['id'])
        align_qc = AlignmentQC(self.probe_id, one=one, brain_atlas=brain_atlas, channels=False)
        align_qc.load_data(prev_alignments=traj['json'], xyz_picks=np.array(self.xyz_picks) / 1e6,
                           cluster_chns=self.cluster_chns)
        align_qc.run(update=True, upload=True)
        insertion = one.alyx.rest('insertions', 'read', id=self.probe_id)
        assert (insertion['json']['qc'] == 'PASS')
        assert (insertion['json']['extended_qc']['_alignment_number'] == 4)
        assert (insertion['json']['extended_qc']['_alignment_stored'] ==
                '2020-06-19T10:52:36_noam.roth')
        assert (insertion['json']['extended_qc']['_alignment_resolved'] == 1)
        assert (insertion['json']['extended_qc']['_alignment_qc'] > 0.8)
        traj = one.alyx.rest('trajectories', 'list', probe_id=self.probe_id,
                             provenance='Ephys aligned histology track')
        assert(self.prev_traj_id != traj[0]['id'])

    @classmethod
    def tearDownClass(cls) -> None:
        one.alyx.rest('insertions', 'delete', id=cls.probe_id)


class TestAlignmentQcManual(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        data = np.load(Path(Path(__file__).parent.
                            joinpath('fixtures', 'data_alignmentqc_manual.npz')),
                       allow_pickle=True)
        # data = np.load('data_alignmentqc_manual.npz', allow_pickle=True)
        cls.xyz_picks = (data['xyz_picks'] * 1e6).tolist()
        cls.alignments = data['alignments'].tolist()
        cls.cluster_chns = data['cluster_chns']

        data = np.load(Path(Path(__file__).parent.
                            joinpath('fixtures', 'data_alignmentqc_existing.npz')),
                       allow_pickle=True)
        insertion = data['insertion'].tolist()
        insertion['json'] = {'xyz_picks': cls.xyz_picks}
        probe_insertion = one.alyx.rest('insertions', 'create', data=insertion)
        cls.probe_id = probe_insertion['id']
        cls.trajectory = data['trajectory'].tolist()
        cls.trajectory.update({'probe_insertion': cls.probe_id})
        cls.trajectory.update({'json': cls.alignments})
        cls.traj = one.alyx.rest('trajectories', 'create', data=cls.trajectory)

    def setUp(self) -> None:
        traj = one.alyx.rest('trajectories', 'list', probe_id=self.probe_id,
                             provenance='Ephys aligned histology track')
        if traj:
            self.prev_traj_id = traj[0]['id']

    def test_01_normal_computation(self):
        align_qc = AlignmentQC(self.probe_id, one=one, brain_atlas=brain_atlas, channels=False)
        align_qc.load_data(prev_alignments=self.traj['json'],
                           xyz_picks=np.array(self.xyz_picks) / 1e6,
                           cluster_chns=self.cluster_chns)
        align_qc.run(update=True, upload=True)
        insertion = one.alyx.rest('insertions', 'read', id=self.probe_id)
        assert (insertion['json']['qc'] == 'WARNING')
        assert(insertion['json']['extended_qc']['alignment'] == 'WARNING')
        assert (insertion['json']['extended_qc']['_alignment_number'] == 3)
        assert (insertion['json']['extended_qc']['_alignment_stored'] ==
                '2020-09-28T15:57:25_mayo')
        assert (insertion['json']['extended_qc']['_alignment_resolved'] == 0)
        assert (insertion['json']['extended_qc']['_alignment_qc'] < 0.8)
        traj = one.alyx.rest('trajectories', 'list', probe_id=self.probe_id,
                             provenance='Ephys aligned histology track')
        assert(self.prev_traj_id == traj[0]['id'])

    def test_02_manual_resolution_latest(self):
        align_qc = AlignmentQC(self.probe_id, one=one, brain_atlas=brain_atlas, channels=False)
        align_qc.load_data(prev_alignments=self.traj['json'],
                           xyz_picks=np.array(self.xyz_picks) / 1e6,
                           cluster_chns=self.cluster_chns)
        align_qc.resolve_manual('2020-09-28T15:57:25_mayo', update=True, upload=True)
        insertion = one.alyx.rest('insertions', 'read', id=self.probe_id)
        assert (insertion['json']['qc'] == 'PASS')
        assert(insertion['json']['extended_qc']['alignment'] == 'WARNING')
        assert(insertion['json']['extended_qc']['alignment_user'] == 'PASS')
        assert (insertion['json']['extended_qc']['_alignment_number'] == 3)
        assert (insertion['json']['extended_qc']['_alignment_stored'] ==
                '2020-09-28T15:57:25_mayo')
        assert (insertion['json']['extended_qc']['_alignment_resolved'] == 1)
        assert (insertion['json']['extended_qc']['_alignment_qc'] < 0.8)
        traj = one.alyx.rest('trajectories', 'list', probe_id=self.probe_id,
                             provenance='Ephys aligned histology track')
        assert(self.prev_traj_id == traj[0]['id'])

    def test_03_manual_resolution_not_latest(self):
        align_qc = AlignmentQC(self.probe_id, one=one, brain_atlas=brain_atlas, channels=False)
        align_qc.load_data(prev_alignments=self.traj['json'],
                           xyz_picks=np.array(self.xyz_picks) / 1e6,
                           cluster_chns=self.cluster_chns)
        align_qc.resolve_manual('2020-09-28T10:03:06_alejandro', update=True, upload=True)
        insertion = one.alyx.rest('insertions', 'read', id=self.probe_id)
        assert (insertion['json']['qc'] == 'PASS')
        assert(insertion['json']['extended_qc']['alignment'] == 'WARNING')
        assert(insertion['json']['extended_qc']['alignment_user'] == 'PASS')
        assert (insertion['json']['extended_qc']['_alignment_number'] == 3)
        assert (insertion['json']['extended_qc']['_alignment_stored'] ==
                '2020-09-28T10:03:06_alejandro')
        assert (insertion['json']['extended_qc']['_alignment_resolved'] == 1)
        assert (insertion['json']['extended_qc']['_alignment_qc'] < 0.8)

        traj = one.alyx.rest('trajectories', 'list', probe_id=self.probe_id,
                             provenance='Ephys aligned histology track')
        assert(self.prev_traj_id != traj[0]['id'])

    @classmethod
    def tearDownClass(cls) -> None:
        one.alyx.rest('insertions', 'delete', id=cls.probe_id)


if __name__ == "__main__":
    unittest.main(exit=False)
